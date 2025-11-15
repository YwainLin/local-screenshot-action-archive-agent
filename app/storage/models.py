"""数据模型定义"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DuplicateKind(str, Enum):
    EXACT = "exact"
    NEAR = "near"


class ProposalAction(str, Enum):
    KEEP = "keep"
    MARK_PENDING = "mark_pending"
    COPY_TO_CATEGORY = "copy_to_category"
    MERGE_DUPLICATE = "merge_duplicate"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class AuditEventType(str, Enum):
    COPY = "copy"
    EXPORT = "export"
    REJECT = "reject"
    ERROR = "error"
    PROPOSAL_APPROVED = "proposal_approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    FILE_COPIED = "file_copied"
    COPY_FAILED = "copy_failed"


class WorkspaceConfig(BaseModel):
    """工作区配置模型"""

    workspace_id: str = Field(..., description="工作区唯一标识")
    root_path: str = Field(..., description="用户选择的截图目录（白名单根目录）")
    allowed_export_paths: list[str] = Field(
        default_factory=list, description="允许导出的目标目录列表"
    )
    thumbnail_max_size: int = Field(default=256, description="缩略图最大尺寸（像素）")
    phash_threshold: int = Field(default=10, description="近似重复 pHash 距离阈值")
    ocr_language: str = Field(default="ch", description="OCR 默认语言")
    enable_local_model: bool = Field(default=False, description="是否启用本地视觉模型")


class ScanRun(BaseModel):
    """扫描任务模型"""

    id: Optional[str] = Field(None, description="任务 ID")
    workspace_id: Optional[str] = Field(None, description="所属工作区 ID")
    root_path: str = Field(..., description="扫描目录路径")
    status: ScanStatus = Field(default=ScanStatus.PENDING, description="任务状态")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    total_files: int = Field(default=0, description="总文件数")
    scanned_files: int = Field(default=0, description="已扫描文件数")
    error_count: int = Field(default=0, description="错误数")
    error_messages: list[str] = Field(default_factory=list, description="错误信息列表")


class Asset(BaseModel):
    """图片资产模型"""

    id: Optional[str] = Field(None, description="资产 ID")
    scan_run_id: str = Field(..., description="所属扫描任务 ID")
    path: str = Field(..., description="文件绝对路径")
    filename: str = Field(..., description="文件名")
    sha256: Optional[str] = Field(None, description="SHA-256 哈希")
    phash: Optional[str] = Field(None, description="感知哈希")
    size: int = Field(..., description="文件大小（字节）")
    mtime: Optional[datetime] = Field(None, description="修改时间")
    width: Optional[int] = Field(None, description="图片宽度")
    height: Optional[int] = Field(None, description="图片高度")
    thumbnail_path: Optional[str] = Field(None, description="缩略图路径")


class DuplicateGroup(BaseModel):
    """重复组模型"""

    id: Optional[str] = Field(None, description="组 ID")
    scan_run_id: str = Field(..., description="所属扫描任务 ID")
    kind: DuplicateKind = Field(..., description="重复类型")
    representative_asset_id: str = Field(..., description="代表图片 ID")
    distance: Optional[int] = Field(None, description="pHash 距离（近似重复）")
    asset_ids: list[str] = Field(default_factory=list, description="组内资产 ID 列表")


class OcrResult(BaseModel):
    """OCR 结果模型"""

    id: Optional[str] = Field(None, description="结果 ID")
    asset_id: str = Field(..., description="关联资产 ID")
    engine: str = Field(..., description="OCR 引擎名称")
    engine_version: str = Field(default="", description="引擎版本")
    language: str = Field(..., description="识别语言")
    text: str = Field(..., description="OCR 识别文本")
    confidence: float = Field(default=0.0, description="置信度 (0-1)")
    is_sensitive: bool = Field(default=False, description="是否包含敏感内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class Extraction(BaseModel):
    """提取实体模型"""

    id: Optional[str] = Field(None, description="实体 ID")
    asset_id: str = Field(..., description="关联资产 ID")
    ocr_result_id: Optional[str] = Field(None, description="关联 OCR 结果 ID")
    kind: str = Field(..., description="实体类型 (date/url/amount/action_phrase)")
    value: str = Field(..., description="原始值")
    value_masked: str = Field(..., description="掩码后的值")
    evidence_span: str = Field(..., description="OCR 证据片段")
    confidence: float = Field(default=0.0, description="置信度 (0-1)")
    is_sensitive: bool = Field(default=False, description="是否敏感内容")
    source: str = Field(default="rule", description="来源 (rule/model_suggestion)")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class ArchiveProposal(BaseModel):
    """归档建议模型"""

    id: Optional[str] = Field(None, description="建议 ID")
    asset_id: str = Field(..., description="关联资产 ID")
    action: ProposalAction = Field(..., description="建议操作")
    suggested_category: Optional[str] = Field(None, description="建议分类")
    target_path: Optional[str] = Field(None, description="目标路径")
    confidence: float = Field(default=0.0, description="置信度 (0-1)")
    rationale: str = Field(default="", description="建议理由")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用列表")
    requires_approval: bool = Field(default=True, description="是否需要审批")
    status: ProposalStatus = Field(default=ProposalStatus.PENDING, description="状态")
    rejection_reason: Optional[str] = Field(None, description="拒绝理由")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class AuditEvent(BaseModel):
    """审计事件模型"""

    id: Optional[str] = Field(None, description="事件 ID")
    proposal_id: str = Field(..., description="关联建议 ID")
    event_type: AuditEventType = Field(..., description="事件类型")
    asset_id: str = Field(..., description="关联资产 ID")
    source_path: str = Field(..., description="源文件路径")
    target_path: Optional[str] = Field(None, description="目标路径")
    before_hash: Optional[str] = Field(None, description="操作前哈希")
    after_hash: Optional[str] = Field(None, description="操作后哈希")
    success: bool = Field(default=True, description="是否成功")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
