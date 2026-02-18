from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, SQLModel

from app.db import get_db
from app.models.models import Report, IssueType, Order, PickTask


class ReportCreate(SQLModel):
    """Schema for creating new reports."""
    order_id: int
    order_number: Optional[str] = None
    task_id: Optional[int] = None
    task_location: Optional[str] = None
    task_sku: Optional[str] = None
    issue_type: IssueType
    message: str


class ReportUpdate(SQLModel):
    """Schema for updating reports."""
    task_id: Optional[int] = None
    task_location: Optional[str] = None
    task_sku: Optional[str] = None
    issue_type: Optional[IssueType] = None
    message: Optional[str] = None


class ReportResponse(SQLModel):
    """Schema for report responses."""
    report_id: int
    order_id: int
    order_number: Optional[str] = None
    task_id: Optional[int] = None
    task_location: Optional[str] = None
    task_sku: Optional[str] = None
    issue_type: IssueType
    message: str
    created_at: str  # ISO format string


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "",
    response_model=List[ReportResponse],
    summary="List reports",
)
@router.get(
    "/",
    response_model=List[ReportResponse],
    summary="List reports",
)
async def list_reports(
    *,
    db: AsyncSession = Depends(get_db),
    order_id: Optional[int] = Query(
        default=None,
        description="Filter by specific order ID",
    ),
    issue_type: Optional[IssueType] = Query(
        default=None,
        description="Filter by issue type",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> List[ReportResponse]:
    """
    List reports with optional filtering.
    
    Returns reports sorted by created_at descending (newest first).
    """
    stmt = select(Report)
    
    # Apply filters
    if order_id is not None:
        stmt = stmt.where(Report.order_id == order_id)
    
    if issue_type is not None:
        stmt = stmt.where(Report.issue_type == issue_type)
    
    # Order by created_at descending and apply pagination
    stmt = stmt.order_by(Report.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    reports = result.scalars().all()
    
    # Convert to response model
    return [
        ReportResponse(
            report_id=r.report_id,
            order_id=r.order_id,
            order_number=r.order_number,
            task_id=r.task_id,
            task_location=r.task_location,
            task_sku=r.task_sku,
            issue_type=r.issue_type,
            message=r.message,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in reports
    ]


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get report by ID",
)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Get a single report by ID."""
    stmt = select(Report).where(Report.report_id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    
    return ReportResponse(
        report_id=report.report_id,
        order_id=report.order_id,
        order_number=report.order_number,
        task_id=report.task_id,
        task_location=report.task_location,
        task_sku=report.task_sku,
        issue_type=report.issue_type,
        message=report.message,
        created_at=report.created_at.isoformat() if report.created_at else "",
    )


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new report",
)
@router.post(
    "/",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new report",
)
async def create_report(
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    Create a new issue report.
    
    Validates that the order exists before creating.
    Optionally validates task_id if provided.
    """
    # Validate order exists
    order_result = await db.execute(
        select(Order).where(Order.order_id == payload.order_id)
    )
    order = order_result.scalar_one_or_none()
    
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {payload.order_id} not found",
        )
    
    # If task_id provided, validate it exists and belongs to the order
    if payload.task_id is not None:
        task_result = await db.execute(
            select(PickTask).where(PickTask.task_id == payload.task_id)
        )
        task = task_result.scalar_one_or_none()
        
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {payload.task_id} not found",
            )
        
        if task.order_id != payload.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task {payload.task_id} does not belong to order {payload.order_id}",
            )
    
    # Use order_number from order if not provided
    order_number = payload.order_number or order.order_number
    
    # Create report
    report = RepINSERT INTO stacking_rules (
        rule_id,
        product_id_top,
        product_id_bottom,
        allowed,
        max_overhang_cm,
        reason
      )
    VALUES (
        rule_id:integer,
        product_id_top:integer,
        product_id_bottom:integer,
        allowed:boolean,
        max_overhang_cm:numeric,
        'reason:character varying'
      );ort(
        order_id=payload.order_id,
        order_number=order_number,
        task_id=payload.task_id,
        task_location=payload.task_location,
        task_sku=payload.task_sku,
        issue_type=payload.issue_type,
        message=payload.message,
    )
    
    db.add(report)
    await db.commit()
    await db.refresh(report)
    
    return ReportResponse(
        report_id=report.report_id,
        order_id=report.order_id,
        order_number=report.order_number,
        task_id=report.task_id,
        task_location=report.task_location,
        task_sku=report.task_sku,
        issue_type=report.issue_type,
        message=report.message,
        created_at=report.created_at.isoformat() if report.created_at else "",
    )


@router.put(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Update a report",
)
async def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    Update an existing report.
    
    Only provided fields will be updated.
    If task_id is provided, validates it exists and belongs to the same order.
    """
    # Get existing report
    stmt = select(Report).where(Report.report_id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    
    # If task_id is being updated, validate it
    if payload.task_id is not None:
        task_result = await db.execute(
            select(PickTask).where(PickTask.task_id == payload.task_id)
        )
        task = task_result.scalar_one_or_none()
        
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {payload.task_id} not found",
            )
        
        if task.order_id != report.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task {payload.task_id} does not belong to order {report.order_id}",
            )
    
    # Update fields
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)
    
    await db.commit()
    await db.refresh(report)
    
    return ReportResponse(
        report_id=report.report_id,
        order_id=report.order_id,
        order_number=report.order_number,
        task_id=report.task_id,
        task_location=report.task_location,
        task_sku=report.task_sku,
        issue_type=report.issue_type,
        message=report.message,
        created_at=report.created_at.isoformat() if report.created_at else "",
    )


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a report",
)
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a report by ID."""
    stmt = select(Report).where(Report.report_id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    
    await db.delete(report)
    await db.commit()
    return None
