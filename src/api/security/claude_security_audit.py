# src/api/security/claude_security_audit.py
"""
Security Audit Framework para Claude Integration
===============================================

Framework de auditoría de seguridad específico para validar
la seguridad de la integración Claude centralizada.

Author: Arquitecto Senior
Version: 1.0.0
"""

import os
import re
import time
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
import httpx

logger = logging.getLogger(__name__)

class SecurityRiskLevel(str, Enum):
    """Niveles de riesgo de seguridad"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityFinding:
    """Hallazgo de seguridad individual"""
    category: str
    risk_level: SecurityRiskLevel
    title: str
    description: str
    affected_component: str
    recommendation: str
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None

class ClaudeSecurityAuditor:
    """
    Auditor de seguridad para la integración Claude
    """
    
    def __init__(self):
        self.findings: List[SecurityFinding] = []
        self.audit_timestamp = time.time()
    
    async def run_comprehensive_audit(self) -> Dict[str, Any]:
        """
        Ejecuta auditoría de seguridad comprehensiva
        """
        logger.info("🔒 Starting comprehensive Claude security audit...")
        
        # Ejecutar todas las auditorías
        audit_results = await asyncio.gather(
            self._audit_api_key_security(),
            self._audit_configuration_security(),
            self._audit_data_protection(),
            self._audit_network_security(),
            self._audit_input_validation(),
            self._audit_rate_limiting(),
            self._audit_logging_security(),
            return_exceptions=True
        )
        
        # Compilar resultados
        total_findings = len(self.findings)
        risk_summary = self._calculate_risk_summary()
        
        return {
            "audit_timestamp": self.audit_timestamp,
            "total_findings": total_findings,
            "risk_summary": risk_summary,
            "findings_by_category": self._group_findings_by_category(),
            "findings_by_risk": self._group_findings_by_risk(),
            "detailed_findings": [asdict(finding) for finding in self.findings],
            "recommendations": self._generate_priority_recommendations(),
            "compliance_status": self._assess_compliance_status(),
            "next_audit_recommended": time.time() + (30 * 24 * 3600)  # 30 días
        }
    
    async def _audit_api_key_security(self) -> None:
        """Audita seguridad de API keys"""
        logger.info("🔑 Auditing API key security...")
        
        try:
            # Verificar configuración de API key
            api_key = os.getenv("ANTHROPIC_API_KEY")
            
            if not api_key:
                self.findings.append(SecurityFinding(
                    category="api_key_security",
                    risk_level=SecurityRiskLevel.CRITICAL,
                    title="Missing ANTHROPIC_API_KEY",
                    description="API key not configured in environment variables",
                    affected_component="Environment Configuration",
                    recommendation="Configure ANTHROPIC_API_KEY in environment variables",
                    cwe_id="CWE-798"
                ))
                return
            
            # Verificar formato de API key
            if not api_key.startswith("sk-ant-api"):
                self.findings.append(SecurityFinding(
                    category="api_key_security",
                    risk_level=SecurityRiskLevel.HIGH,
                    title="Invalid API Key Format",
                    description="ANTHROPIC_API_KEY does not match expected format",
                    affected_component="Environment Configuration",
                    recommendation="Verify API key format with Anthropic documentation",
                    cwe_id="CWE-798"
                ))
            
            # Verificar longitud de API key (debe ser suficientemente larga)
            if len(api_key) < 50:
                self.findings.append(SecurityFinding(
                    category="api_key_security",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="Short API Key",
                    description="API key appears to be shorter than expected",
                    affected_component="Environment Configuration",
                    recommendation="Verify API key completeness",
                    cwe_id="CWE-798"
                ))
            
            # Verificar que no esté hardcodeada en código
            await self._check_hardcoded_credentials()
            
        except Exception as e:
            logger.error(f"Error in API key security audit: {e}")
    
    async def _audit_configuration_security(self) -> None:
        """Audita seguridad de configuración"""
        logger.info("⚙️ Auditing configuration security...")
        
        try:
            from src.api.core.claude_config import get_claude_config_service
            
            claude_service = get_claude_config_service()
            
            # Verificar configuración de timeout
            if claude_service.timeout > 60:
                self.findings.append(SecurityFinding(
                    category="configuration_security",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="High Timeout Configuration",
                    description=f"Claude timeout set to {claude_service.timeout}s, may enable DoS",
                    affected_component="Claude Configuration",
                    recommendation="Reduce timeout to maximum 30 seconds",
                    cwe_id="CWE-400"
                ))
            
            # Verificar configuración de reintentos
            if claude_service.max_retries > 5:
                self.findings.append(SecurityFinding(
                    category="configuration_security",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="High Retry Configuration",
                    description=f"Max retries set to {claude_service.max_retries}, may amplify costs",
                    affected_component="Claude Configuration",
                    recommendation="Limit max retries to 3-5 attempts",
                    cwe_id="CWE-400"
                ))
            
            # Verificar configuración de desarrollo en producción
            debug_mode = os.getenv("DEBUG", "false").lower()
            if debug_mode in ["true", "1", "yes"]:
                self.findings.append(SecurityFinding(
                    category="configuration_security",
                    risk_level=SecurityRiskLevel.HIGH,
                    title="Debug Mode Enabled",
                    description="Debug mode enabled, may expose sensitive information",
                    affected_component="Environment Configuration",
                    recommendation="Disable debug mode in production environments",
                    cwe_id="CWE-489"
                ))
            
        except Exception as e:
            logger.error(f"Error in configuration security audit: {e}")
    
    async def _audit_data_protection(self) -> None:
        """Audita protección de datos"""
        logger.info("🛡️ Auditing data protection...")
        
        try:
            # Verificar configuración de logs
            log_level = os.getenv("LOG_LEVEL", "INFO")
            if log_level.upper() == "DEBUG":
                self.findings.append(SecurityFinding(
                    category="data_protection",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="Debug Logging Enabled",
                    description="Debug logging may expose sensitive data in logs",
                    affected_component="Logging Configuration",
                    recommendation="Use INFO or WARNING log level in production",
                    cwe_id="CWE-532"
                ))
            
            # Verificar configuración de Redis (datos en tránsito)
            redis_ssl = os.getenv("REDIS_SSL", "false").lower()
            if redis_ssl not in ["true", "1", "yes"]:
                redis_password = os.getenv("REDIS_PASSWORD")
                if redis_password:
                    self.findings.append(SecurityFinding(
                        category="data_protection",
                        risk_level=SecurityRiskLevel.MEDIUM,
                        title="Redis Connection Not Encrypted",
                        description="Redis connection not using SSL/TLS encryption",
                        affected_component="Redis Configuration",
                        recommendation="Enable REDIS_SSL=true for encrypted connections",
                        cwe_id="CWE-319"
                    ))
            
            # Verificar manejo de PII en conversaciones
            await self._check_pii_handling()
            
        except Exception as e:
            logger.error(f"Error in data protection audit: {e}")
    
    async def _audit_network_security(self) -> None:
        """Audita seguridad de red"""
        logger.info("🌐 Auditing network security...")
        
        try:
            # Verificar configuración CORS
            cors_origins = os.getenv("CORS_ORIGINS", "*")
            if cors_origins == "*":
                self.findings.append(SecurityFinding(
                    category="network_security",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="Permissive CORS Configuration",
                    description="CORS allows all origins (*), potential security risk",
                    affected_component="CORS Configuration",
                    recommendation="Restrict CORS to specific trusted domains",
                    cwe_id="CWE-346"
                ))
            
            # Verificar HTTPS enforcement
            force_https = os.getenv("FORCE_HTTPS", "false").lower()
            if force_https not in ["true", "1", "yes"]:
                self.findings.append(SecurityFinding(
                    category="network_security",
                    risk_level=SecurityRiskLevel.HIGH,
                    title="HTTPS Not Enforced",
                    description="HTTPS not enforced, data may be transmitted insecurely",
                    affected_component="HTTP Configuration",
                    recommendation="Enable FORCE_HTTPS=true for production",
                    cwe_id="CWE-319"
                ))
            
            # Verificar configuración de headers de seguridad
            await self._check_security_headers()
            
        except Exception as e:
            logger.error(f"Error in network security audit: {e}")
    
    async def _audit_input_validation(self) -> None:
        """Audita validación de entrada"""
        logger.info("✅ Auditing input validation...")
        
        try:
            # Verificar límites de input
            max_message_length = 10000  # Límite razonable
            
            # Simular test de input largo
            test_cases = [
                {"type": "long_input", "size": max_message_length + 1},
                {"type": "special_chars", "content": "<script>alert('xss')</script>"},
                {"type": "sql_injection", "content": "'; DROP TABLE users; --"},
                {"type": "command_injection", "content": "; rm -rf /"},
            ]
            
            for test_case in test_cases:
                # En una implementación real, aquí harías requests de prueba
                # Por ahora, asumimos que necesitamos validación
                pass
            
            # Verificar que existe validación de entrada
            self.findings.append(SecurityFinding(
                category="input_validation",
                risk_level=SecurityRiskLevel.LOW,
                title="Input Validation Audit Required",
                description="Manual review of input validation mechanisms recommended",
                affected_component="API Endpoints",
                recommendation="Implement comprehensive input validation and sanitization",
                cwe_id="CWE-20"
            ))
            
        except Exception as e:
            logger.error(f"Error in input validation audit: {e}")
    
    async def _audit_rate_limiting(self) -> None:
        """Audita rate limiting"""
        logger.info("⏱️ Auditing rate limiting...")
        
        try:
            # Verificar configuración de rate limiting
            rate_limit_config = {
                "claude_requests_per_minute": os.getenv("CLAUDE_REQUESTS_PER_MINUTE"),
                "claude_tokens_per_minute": os.getenv("CLAUDE_TOKENS_PER_MINUTE"),
                "api_rate_limit": os.getenv("API_RATE_LIMIT")
            }
            
            missing_limits = [key for key, value in rate_limit_config.items() if not value]
            
            if missing_limits:
                self.findings.append(SecurityFinding(
                    category="rate_limiting",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="Missing Rate Limiting Configuration",
                    description=f"Rate limiting not configured for: {', '.join(missing_limits)}",
                    affected_component="API Configuration",
                    recommendation="Implement rate limiting to prevent abuse and DoS attacks",
                    cwe_id="CWE-400"
                ))
            
            # Verificar límites específicos de Claude
            claude_rpm = os.getenv("CLAUDE_REQUESTS_PER_MINUTE")
            if claude_rpm and int(claude_rpm) > 1000:
                self.findings.append(SecurityFinding(
                    category="rate_limiting",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="High Claude Rate Limit",
                    description=f"Claude rate limit set to {claude_rpm} requests/minute",
                    affected_component="Claude Configuration",
                    recommendation="Consider lower rate limits to prevent cost abuse",
                    cwe_id="CWE-400"
                ))
            
        except Exception as e:
            logger.error(f"Error in rate limiting audit: {e}")
    
    async def _audit_logging_security(self) -> None:
        """Audita seguridad de logging"""
        logger.info("📝 Auditing logging security...")
        
        try:
            # Verificar configuración de logs
            log_file = os.getenv("LOG_FILE")
            if log_file and not log_file.startswith("/var/log/"):
                self.findings.append(SecurityFinding(
                    category="logging_security",
                    risk_level=SecurityRiskLevel.LOW,
                    title="Log File Location",
                    description="Log files not in standard secure location",
                    affected_component="Logging Configuration",
                    recommendation="Store logs in /var/log/ or similar secure location",
                    cwe_id="CWE-532"
                ))
            
            # Verificar rotación de logs
            log_rotation = os.getenv("LOG_ROTATION_ENABLED", "false").lower()
            if log_rotation not in ["true", "1", "yes"]:
                self.findings.append(SecurityFinding(
                    category="logging_security",
                    risk_level=SecurityRiskLevel.LOW,
                    title="Log Rotation Not Configured",
                    description="Log rotation not enabled, may cause disk space issues",
                    affected_component="Logging Configuration",
                    recommendation="Enable log rotation to manage disk space",
                    cwe_id="CWE-400"
                ))
            
        except Exception as e:
            logger.error(f"Error in logging security audit: {e}")
    
    async def _check_hardcoded_credentials(self) -> None:
        """Verifica credenciales hardcodeadas en código"""
        try:
            # Patrones de búsqueda para credenciales
            credential_patterns = [
                r'sk-ant-api[0-9a-zA-Z\-_]{40,}',  # Anthropic API keys
                r'ANTHROPIC_API_KEY\s*=\s*["\'][^"\']+["\']',  # Hardcoded API key
                r'api_key\s*=\s*["\']sk-ant[^"\']+["\']',  # API key assignments
            ]
            
            # Archivos a revisar
            files_to_check = [
                "src/api/core/claude_config.py",
                "src/api/integrations/ai/ai_conversation_manager.py",
                "src/api/mcp/engines/mcp_personalization_engine.py"
            ]
            
            for file_path in files_to_check:
                try:
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        for pattern in credential_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                self.findings.append(SecurityFinding(
                                    category="api_key_security",
                                    risk_level=SecurityRiskLevel.CRITICAL,
                                    title="Hardcoded Credentials Detected",
                                    description=f"Potential hardcoded credentials found in {file_path}",
                                    affected_component=file_path,
                                    recommendation="Remove hardcoded credentials and use environment variables",
                                    cwe_id="CWE-798"
                                ))
                except Exception as e:
                    logger.warning(f"Could not check file {file_path}: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking hardcoded credentials: {e}")
    
    async def _check_pii_handling(self) -> None:
        """Verifica manejo de información personal"""
        try:
            # Verificar configuración de anonimización
            anonymize_pii = os.getenv("ANONYMIZE_PII", "false").lower()
            if anonymize_pii not in ["true", "1", "yes"]:
                self.findings.append(SecurityFinding(
                    category="data_protection",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="PII Anonymization Not Enabled",
                    description="Personal information may not be anonymized in logs/storage",
                    affected_component="Data Processing",
                    recommendation="Enable PII anonymization for GDPR compliance",
                    cwe_id="CWE-359"
                ))
            
            # Verificar política de retención de datos
            data_retention_days = os.getenv("DATA_RETENTION_DAYS")
            if not data_retention_days:
                self.findings.append(SecurityFinding(
                    category="data_protection",
                    risk_level=SecurityRiskLevel.MEDIUM,
                    title="Data Retention Policy Not Defined",
                    description="No data retention policy configured",
                    affected_component="Data Management",
                    recommendation="Define and implement data retention policy",
                    cwe_id="CWE-359"
                ))
                
        except Exception as e:
            logger.error(f"Error checking PII handling: {e}")
    
    async def _check_security_headers(self) -> None:
        """Verifica headers de seguridad"""
        try:
            # Headers de seguridad recomendados
            security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                "Content-Security-Policy": "default-src 'self'"
            }
            
            # En una implementación real, harías una request HTTP para verificar headers
            # Por ahora, asumimos que necesitan ser configurados
            self.findings.append(SecurityFinding(
                category="network_security",
                risk_level=SecurityRiskLevel.MEDIUM,
                title="Security Headers Review Required",
                description="Security headers should be reviewed and configured",
                affected_component="HTTP Configuration",
                recommendation="Implement standard security headers (CSP, HSTS, etc.)",
                cwe_id="CWE-693"
            ))
            
        except Exception as e:
            logger.error(f"Error checking security headers: {e}")
    
    def _calculate_risk_summary(self) -> Dict[str, int]:
        """Calcula resumen de riesgos"""
        summary = {level.value: 0 for level in SecurityRiskLevel}
        for finding in self.findings:
            summary[finding.risk_level.value] += 1
        return summary
    
    def _group_findings_by_category(self) -> Dict[str, List[Dict]]:
        """Agrupa hallazgos por categoría"""
        by_category = {}
        for finding in self.findings:
            if finding.category not in by_category:
                by_category[finding.category] = []
            by_category[finding.category].append(asdict(finding))
        return by_category
    
    def _group_findings_by_risk(self) -> Dict[str, List[Dict]]:
        """Agrupa hallazgos por nivel de riesgo"""
        by_risk = {}
        for finding in self.findings:
            risk_level = finding.risk_level.value
            if risk_level not in by_risk:
                by_risk[risk_level] = []
            by_risk[risk_level].append(asdict(finding))
        return by_risk
    
    def _generate_priority_recommendations(self) -> List[Dict[str, Any]]:
        """Genera recomendaciones priorizadas"""
        recommendations = []
        
        # Priorizar por nivel de riesgo
        risk_priority = [SecurityRiskLevel.CRITICAL, SecurityRiskLevel.HIGH, SecurityRiskLevel.MEDIUM, SecurityRiskLevel.LOW]
        
        for risk_level in risk_priority:
            risk_findings = [f for f in self.findings if f.risk_level == risk_level]
            if risk_findings:
                recommendations.append({
                    "priority": risk_level.value,
                    "count": len(risk_findings),
                    "actions": list(set([f.recommendation for f in risk_findings]))
                })
        
        return recommendations
    
    def _assess_compliance_status(self) -> Dict[str, Any]:
        """Evalúa estado de cumplimiento"""
        critical_count = len([f for f in self.findings if f.risk_level == SecurityRiskLevel.CRITICAL])
        high_count = len([f for f in self.findings if f.risk_level == SecurityRiskLevel.HIGH])
        
        if critical_count > 0:
            status = "non_compliant"
            message = f"{critical_count} critical security issues found"
        elif high_count > 3:
            status = "partially_compliant"
            message = f"{high_count} high-risk security issues found"
        elif high_count > 0:
            status = "mostly_compliant"
            message = f"{high_count} high-risk issues require attention"
        else:
            status = "compliant"
            message = "No critical or high-risk security issues found"
        
        return {
            "status": status,
            "message": message,
            "critical_issues": critical_count,
            "high_risk_issues": high_count,
            "recommendation": "Address critical and high-risk issues immediately"
        }

# Función de conveniencia para auditoría
async def run_claude_security_audit() -> Dict[str, Any]:
    """
    Ejecuta auditoría de seguridad completa para Claude
    """
    auditor = ClaudeSecurityAuditor()
    return await auditor.run_comprehensive_audit()