"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class Project(BaseModel):
    """
    Projects collection schema
    Collection name: "project"
    """
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    status: str = Field("planned", description="Current status: planned, active, on-hold, completed")
    owner: Optional[str] = Field(None, description="Project owner")
    start_date: Optional[date] = Field(None, description="Planned or actual start date")
    end_date: Optional[date] = Field(None, description="Planned or actual end date")
    progress: int = Field(0, ge=0, le=100, description="Percent complete")
    priority: Optional[str] = Field(None, description="Priority: low, medium, high, critical")
    tags: List[str] = Field(default_factory=list, description="Hashtags/labels")

class Task(BaseModel):
    """
    Tasks collection schema
    Collection name: "task"
    """
    project_id: str = Field(..., description="Related project _id as string")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task details")
    status: str = Field("open", description="open, in-progress, blocked, done")
    assignee: Optional[str] = Field(None, description="Assigned person")
    due_date: Optional[date] = Field(None, description="Due date")
    priority: Optional[str] = Field(None, description="Priority: low, medium, high, critical")

class Note(BaseModel):
    """
    Notes collection schema
    Collection name: "note"
    """
    project_id: str = Field(..., description="Related project _id as string")
    author: Optional[str] = Field(None, description="Note author")
    content: str = Field(..., description="Free-form note content")
