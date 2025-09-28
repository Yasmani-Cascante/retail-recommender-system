# src/api/monitoring/__init__.py
"""
Advanced monitoring module for Claude integration
================================================

This module provides comprehensive monitoring, metrics, and alerting for Claude.
"""

from .claude_monitoring import (
    get_claude_metrics, 
    get_claude_historical_metrics, 
    get_claude_alerts,
    record_claude_request,
    claude_metrics_collector
)

__all__ = [
    'get_claude_metrics', 
    'get_claude_historical_metrics', 
    'get_claude_alerts',
    'record_claude_request',
    'claude_metrics_collector'
]
