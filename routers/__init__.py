# routers/__init__.py
"""
Router modules for HR Recruitment App API endpoints
"""

from .auth import router as auth_router
from .employee import router as employee_router
from .manager import router as manager_router

__all__ = ["auth_router", "employee_router", "manager_router"]