from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


class ScanStatus(str, enum.Enum):
    """扫描任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DuplicateKind(str, enum.Enum):
    """重复类型"""
    EXACT = "exact"
    NEAR = "near"


class ProposalAction(str, enum.Enum):
    """归档建议动作"""
    COPY_TO_CATEGORY = "copy_to_category"
    KEEP_IN_PLACE = "keep_in_place"
    MARK_AS_DUPLICATE = "mark_as_duplicate"
    NEEDS_REVIEW = "needs_review"


class ProposalStatus(str, enum.Enum):
    """归档建议状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class AuditEventType(str, enum.Enum):
    """审计事件类型"""
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    FILE_COPIED = "file_copied"
    COPY_FAILED = "copy_failed"


class ScanRun(Base):
    """扫描任务记录"""
    __tablename__ = "scan_run"

    id = Column(String(36), primary_key=True)
    root_path = Column(Text, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(Enum(ScanStatus), default=ScanStatus.PENDING, nullable=False)
    total_files = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_list = Column(Text, default="[]")

    assets = relationship("Asset", back_populates="scan_run")


class Asset(Base):
    """图片资产索引"""
    __tablename__ = "asset"

    id = Column(String(36), primary_key=True)
    scan_run_id = Column(String(36), ForeignKey("scan_run.id"), nullable=False)
    path = Column(Text, nullable=False)
    filename = Column(String(255), nullable=False)
    extension = Column(String(10), nullable=False)
    sha256 = Column(String(64), nullable=False)
    phash = Column(String(16), nullable=True)
    size = Column(Integer, nullable=False)
    mtime = Column(DateTime, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scan_run = relationship("ScanRun", back_populates="assets")
    ocr_results = relationship("OcrResult", back_populates="asset")
    extractions = relationship("Extraction", back_populates="asset")
    proposals = relationship("ArchiveProposal", back_populates="asset")


class DuplicateGroup(Base):
    """重复组"""
    __tablename__ = "duplicate_group"

    id = Column(String(36), primary_key=True)
    kind = Column(Enum(DuplicateKind), nullable=False)
    representative_asset_id = Column(
        String(36), ForeignKey("asset.id"), nullable=False
    )
    distance = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    representative = relationship("Asset", foreign_keys=[representative_asset_id])


class OcrResult(Base):
    """OCR 识别结果"""
    __tablename__ = "ocr_result"

    id = Column(String(36), primary_key=True)
    asset_id = Column(String(36), ForeignKey("asset.id"), nullable=False)
    engine = Column(String(50), nullable=False)
    engine_version = Column(String(50), nullable=True)
    language = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    asset = relationship("Asset", back_populates="ocr_results")


class Extraction(Base):
    """规则提取结果"""
    __tablename__ = "extraction"

    id = Column(String(36), primary_key=True)
    asset_id = Column(String(36), ForeignKey("asset.id"), nullable=False)
    kind = Column(String(50), nullable=False)
    value_raw = Column(Text, nullable=False)
    value_masked = Column(Text, nullable=False)
    evidence_span = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False)
    is_sensitive = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    asset = relationship("Asset", back_populates="extractions")


class ArchiveProposal(Base):
    """归档建议"""
    __tablename__ = "archive_proposal"

    id = Column(String(36), primary_key=True)
    asset_id = Column(String(36), ForeignKey("asset.id"), nullable=False)
    action = Column(Enum(ProposalAction), nullable=False)
    target_category = Column(String(100), nullable=True)
    target_path = Column(Text, nullable=True)
    rationale = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING, nullable=False)
    evidence_refs = Column(Text, default="[]")
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asset = relationship("Asset", back_populates="proposals")


class AuditEvent(Base):
    """审计事件记录（只追加）"""
    __tablename__ = "audit_event"

    id = Column(String(36), primary_key=True)
    proposal_id = Column(String(36), ForeignKey("archive_proposal.id"), nullable=True)
    event_type = Column(Enum(AuditEventType), nullable=False)
    before_hash = Column(String(64), nullable=True)
    after_hash = Column(String(64), nullable=True)
    source_path = Column(Text, nullable=True)
    target_path = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DuplicateGroupMember(Base):
    """重复组成员关系"""
    __tablename__ = "duplicate_group_member"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(36), ForeignKey("duplicate_group.id"), nullable=False)
    asset_id = Column(String(36), ForeignKey("asset.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "asset_id", name="uq_group_asset"),
    )
