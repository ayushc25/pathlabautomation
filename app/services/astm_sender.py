"""Client for sending ASTM commands (Host Queries / Orders) to an analyzer."""
from __future__ import annotations

import socket
import time
from typing import List

from app.services.checksum import compute_checksum
from app.utils.logger import get_logger

logger = get_logger(__name__)

ENQ = b"\x05"
ACK = b"\x06"
NAK = b"\x15"
EOT = b"\x04"
STX = b"\x02"
ETX = b"\x03"
CR = b"\x0D"
LF = b"\x0A"

def _format_frame(frame_number: int, record: str) -> bytes:
    """Format an ASTM frame with STX, frame number, record, CR, ETX, checksum, CR, LF."""
    # frame_number is 1 to 7, then 0. 
    fn_str = str(frame_number % 8).encode("ascii")
    record_bytes = record.encode("latin-1", errors="replace")
    
    # Payload for checksum starts at frame number and ends at ETX
    payload = fn_str + record_bytes + CR + ETX
    checksum = compute_checksum(payload).encode("ascii")
    
    return STX + payload + checksum + CR + LF


import queue

def push_astm_order(
    listener, 
    sample_id: str, 
    patient_id: str, 
    test_ids: List[str], 
    patient_name: str = "", 
    dob: str = "", 
    gender: str = ""
) -> str:
    """Queue a new test order to be pushed over the active analyzer connection."""
    tests_str = "\\".join([f"^^^{tid}" for tid in test_ids])
    
    records = [
        f"H|\\^&|||Host|||||||P|1",
        f"P|1||{patient_id}||{patient_name}||{dob}|{gender}||||||",
        f"O|1|{sample_id}||{tests_str}|||||||||||||||||||||",
        f"L|1|N"
    ]
    
    if not listener or not listener.is_running():
        return "Error: No active connection to the analyzer. Wait for the analyzer to connect first."
        
    result_queue = queue.Queue()
    listener.outbound_queue.put((records, result_queue))
    
    try:
        # Wait up to 10 seconds for the listener thread to transmit and return the log
        result_log = result_queue.get(timeout=10.0)
        return result_log
    except queue.Empty:
        return "Error: Timed out waiting for the analyzer to accept the order. The connection might be busy or broken."
