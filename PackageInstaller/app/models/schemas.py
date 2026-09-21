"""Pydantic response models for the /decode endpoint.

Result/histogram/matrix contents are intentionally typed loosely
(``Dict[str, Any]`` / ``List[...]``) since parameter names and payload
shapes come from the analyzer at runtime and must never be hardcoded.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NameParts(BaseModel):
    last: Optional[str] = None
    first: Optional[str] = None
    middle: Optional[str] = None


class Patient(BaseModel):
    patient_id: Optional[str] = None
    name: NameParts = Field(default_factory=NameParts)
    dob: Optional[str] = None
    sex: Optional[str] = None
    race: Optional[str] = None
    physician: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None


class Order(BaseModel):
    sample_id: Optional[str] = None
    instrument_sample_id: Optional[str] = None
    tests: List[str] = Field(default_factory=list)
    priority: Optional[str] = None
    collection_datetime: Optional[str] = None
    collection_end_datetime: Optional[str] = None
    action_code: Optional[str] = None
    report_type: Optional[str] = None


class ReferenceRange(BaseModel):
    low: Optional[Any] = None
    high: Optional[Any] = None
    raw: Optional[str] = None


class ResultEntry(BaseModel):
    code: Optional[str] = None
    test_name: Optional[str] = None
    panel: Optional[str] = None
    value: Optional[Any] = None
    unit: Optional[str] = None
    reference_range: Optional[Dict[str, Any]] = None
    flags: List[str] = Field(default_factory=list)
    status: Optional[str] = None
    timestamp: Optional[str] = None


class Comment(BaseModel):
    source: Optional[str] = None
    alarm_type: Optional[str] = None
    description: Optional[str] = None
    measurement: Optional[str] = None
    raw: Optional[str] = None


class Histogram(BaseModel):
    type: str
    name: Optional[str] = None
    x: List[float]
    y: List[float]


class MatrixPoint(BaseModel):
    x: float
    y: float


class Matrix(BaseModel):
    type: str
    name: Optional[str] = None
    points: List[MatrixPoint]


class DecodeMeta(BaseModel):
    header: Dict[str, Any] = Field(default_factory=dict)
    frames_parsed: int = 0
    records_parsed: int = 0
    records_skipped: int = 0
    checksum_failures: int = 0
    warnings: List[str] = Field(default_factory=list)


class DecodeResponse(BaseModel):
    patient: Patient = Field(default_factory=Patient)
    order: Order = Field(default_factory=Order)
    results: Dict[str, ResultEntry] = Field(default_factory=dict)
    comments: List[Comment] = Field(default_factory=list)
    histograms: Dict[str, Histogram] = Field(default_factory=dict)
    matrices: Dict[str, Matrix] = Field(default_factory=dict)
    images: Dict[str, str] = Field(default_factory=dict)
    meta: DecodeMeta = Field(default_factory=DecodeMeta)


class ErrorResponse(BaseModel):
    detail: str
