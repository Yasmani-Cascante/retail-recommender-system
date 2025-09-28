# src/api/security/__init__.py
"""
Security module for Claude integration
=====================================

This module provides security audit capabilities for the Claude integration.
"""

from .claude_security_audit import run_claude_security_audit

__all__ = ['run_claude_security_audit']
