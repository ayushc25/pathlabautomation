"""Background TCP listener for analyzer traffic."""
from __future__ import annotations

import queue
import socket
import threading
import time
from typing import Optional

from app.services.astm_parser import ASTMParseError
from app.services.database import save_raw_capture
from app.services.report_generator import generate_report
from app.utils.logger import get_logger

logger = get_logger(__name__)

ENQ = b"\x05"
ACK = b"\x06"
EOT = b"\x04"


class AnalyzerListener:
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.outbound_queue = queue.Queue()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="AnalyzerListener")
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def ensure_running(self) -> bool:
        if self.is_running():
            return False
        self.start()
        return True

    def _run(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.host, self.port))
                server.listen(1)
                server.settimeout(1.0)
                logger.info("Analyzer listener active on %s:%s", self.host, self.port)

                while not self._stop_event.is_set():
                    try:
                        conn, addr = server.accept()
                    except socket.timeout:
                        continue

                    logger.info("Analyzer connected from %s", addr)
                    with conn:
                        transcript = bytearray()

                        def flush_transcript() -> None:
                            if not transcript:
                                return
                            raw_bytes = bytes(transcript)
                            raw_text = raw_bytes.decode("latin-1", errors="replace")
                            raw_capture_id = save_raw_capture(source="socket", payload=raw_text)
                            logger.info(
                                "Received %d bytes from analyzer (raw_capture_id=%s)",
                                len(raw_bytes), raw_capture_id,
                            )

                            try:
                                report = generate_report(
                                    raw_bytes,
                                    source="socket",
                                    raw_capture_id=raw_capture_id,
                                )
                            except ASTMParseError as exc:
                                logger.error(
                                    "Could not decode analyzer transmission (raw_capture_id=%s): %s",
                                    raw_capture_id, exc,
                                )
                            except Exception:
                                logger.exception(
                                    "Unexpected error decoding analyzer transmission (raw_capture_id=%s)",
                                    raw_capture_id,
                                )
                            else:
                                order_number = report.get("order", {}).get("sample_id")
                                patient_id = report.get("patient", {}).get("patient_id")
                                
                                # Auto-detect and register machine
                                sender_name = report.get("meta", {}).get("header", {}).get("sender_name")
                                if sender_name:
                                    clean_name = sender_name.replace('^', ' ').replace('_', ' ').strip()
                                    if clean_name:
                                        from app.services.database import load_users, upsert_user, upsert_machine
                                        users = load_users()
                                        user_id = users[0]["id"] if users else upsert_user("Sk lab")
                                        upsert_machine(user_id, clean_name)
                                        logger.info("Auto-registered machine from ASTM header: %s", clean_name)
                                        
                                logger.info(
                                    "Decoded result from analyzer: raw_capture_id=%s order=%s patient=%s "
                                    "results=%d warnings=%d",
                                    raw_capture_id, order_number, patient_id,
                                    len(report.get("results", {})), len(report.get("meta", {}).get("warnings", [])),
                                )

                            transcript.clear()

                        while not self._stop_event.is_set():
                            conn.settimeout(0.5)
                            try:
                                data = conn.recv(4096)
                            except socket.timeout:
                                try:
                                    outbound_item = self.outbound_queue.get_nowait()
                                    records, result_queue = outbound_item
                                    self._send_astm_order(conn, records, result_queue)
                                except queue.Empty:
                                    pass
                                continue

                            if not data:
                                flush_transcript()
                                break

                            transcript.extend(data)
                            logger.debug("Received socket chunk (%s bytes)", len(data))

                            if data == ENQ:
                                conn.sendall(ACK)
                                continue
                            if data == EOT:
                                flush_transcript()
                                continue
                            conn.sendall(ACK)
        except Exception:
            logger.exception("Analyzer listener crashed")
            raise

    def _send_astm_order(self, conn: socket.socket, records: list[str], result_queue: queue.Queue) -> None:
        from app.services.astm_sender import _format_frame
        log_messages = []
        try:
            conn.settimeout(5.0)
            log_messages.append("Attempting to push order over active connection...")
            
            # Send ENQ
            conn.sendall(ENQ)
            log_messages.append("Host -> <ENQ>")
            
            response = conn.recv(1)
            if response == ACK:
                log_messages.append("Instrument -> <ACK>")
            else:
                log_messages.append(f"Expected <ACK>, got {response}")
                conn.sendall(EOT)
                result_queue.put("\n".join(log_messages))
                return
                
            # Send Frames
            frame_num = 1
            for record in records:
                frame_data = _format_frame(frame_num, record)
                conn.sendall(frame_data)
                log_messages.append(f"Host -> <STX>{frame_num}...{record[:20]}...<CR><ETX>xx<CR><LF>")
                
                response = conn.recv(1)
                if response == ACK:
                    log_messages.append("Instrument -> <ACK>")
                else:
                    log_messages.append(f"Expected <ACK> for frame {frame_num}, got {response}")
                    break
                    
                frame_num += 1
                
            # Send EOT
            conn.sendall(EOT)
            log_messages.append("Host -> <EOT>")
            
        except Exception as e:
            log_messages.append(f"Error pushing order: {e}")
            logger.exception("Error pushing order over active connection")
            
        result_queue.put("\n".join(log_messages))
