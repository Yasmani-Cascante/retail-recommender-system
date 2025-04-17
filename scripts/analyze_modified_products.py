#!/usr/bin/env python
"""
Script para analizar los productos modificados durante la validación.

Este script lee los archivos de registro generados por el validador de productos
y proporciona un análisis detallado de las modificaciones realizadas.
"""

import os
import json
import argparse
from typing import Dict, List, Any
from datetime import datetime

def parse_args():
    """Parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(description="Analizar productos modificados durante la validación")
    parser.add_argument(
        "--log-file", 
        help="Ruta al archivo de registro de productos modificados",
        default=None
    )
    parser.add_argument(
        "--log-dir", 
        help="Directorio con archivos de registro (si no se especifica un archivo)",
        default="logs/product_validation"
    )
    parser.add_argument(
        "--output",
        help="Archivo de salida para el informe (opcional)",
        default=None
    )
    
    return parser.parse_args()

def find_latest_log_file(log_dir: str) -> str:
    """
    Encuentra el archivo de registro más reciente en el directorio.
    
    Args:
        log_dir: Directorio con archivos de registro.
        
    Returns:
        Ruta al archivo de registro más reciente.
    """
    if not os.path.exists(log_dir):
        print(f"Error: El directorio {log_dir} no existe.")
        return None
        
    log_files = [f for f in os.listdir(log_dir) if f.startswith("modified_products_") and f.endswith(".jsonl")]
    
    if not log_files:
        print(f"Error: No se encontraron archivos de registro en {log_dir}.")
        return None
        
    # Ordenar por fecha de modificación (más reciente primero)
    log_files.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
    
    return os.path.join(log_dir, log_files[0])

def read_log_file(file_path: str) -> List[Dict]:
    """
    Lee un archivo de registro de productos modificados.
    
    Args:
        file_path: Ruta al archivo de registro.
        
    Returns:
        Lista de entradas de registro.
    """
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        return []
        
    entries = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    print(f"Error: Formato de línea inválido: {line}")
    
    return entries

def analyze_modifications(entries: List[Dict]) -> Dict[str, Any]:
    """
    Analiza las modificaciones realizadas en los productos.
    
    Args:
        entries: Lista de entradas de registro.
        
    Returns:
        Diccionario con análisis de modificaciones.
    """
    if not entries:
        return {
            "total_products": 0,
            "modification_types": {},
            "summary": "No hay datos para analizar."
        }
    
    # Estadísticas generales
    total_products = len(entries)
    
    # Contar tipos de modificaciones
    modification_types = {}
    for entry in entries:
        for mod in entry.get("modifications", []):
            modification_types[mod] = modification_types.get(mod, 0) + 1
    
    # Productos por tipo de modificación
    products_by_modification = {}
    for mod_type in modification_types:
        products_by_modification[mod_type] = [
            entry.get("product_id") for entry in entries 
            if mod_type in entry.get("modifications", [])
        ]
    
    # Análisis de descripciones resumidas
    description_summaries = []
    for entry in entries:
        if "description_summarized" in entry.get("modifications", []):
            original = None
            modified = None
            
            # Buscar campo de descripción en los datos originales y modificados
            for field in ["body_html", "description"]:
                if field in entry.get("original", {}):
                    original = entry["original"][field]
                if field in entry.get("modified", {}):
                    modified = entry["modified"][field]
            
            if original and modified:
                description_summaries.append({
                    "product_id": entry.get("product_id"),
                    "original_length": len(original) if isinstance(original, str) else 0,
                    "modified_length": len(modified) if isinstance(modified, str) else 0,
                    "reduction_percent": round(
                        100 - (len(modified) / len(original) * 100) 
                        if isinstance(original, str) and isinstance(modified, str) and len(original) > 0 
                        else 0, 
                        2
                    )
                })
    
    # Productos con múltiples modificaciones
    products_with_multiple_mods = [
        {"product_id": entry.get("product_id"), "modifications": entry.get("modifications")}
        for entry in entries
        if len(entry.get("modifications", [])) > 1
    ]
    
    return {
        "timestamp": datetime.now().isoformat(),
        "log_file": os.path.basename(args.log_file) if args.log_file else "desconocido",
        "total_products": total_products,
        "modification_types": modification_types,
        "most_common_modifications": sorted(
            modification_types.items(), 
            key=lambda x: x[1], 
            reverse=True
        ),
        "description_summaries": description_summaries,
        "avg_description_reduction": round(
            sum(item["reduction_percent"] for item in description_summaries) / len(description_summaries) 
            if description_summaries else 0, 
            2
        ),
        "products_with_multiple_mods": products_with_multiple_mods,
        "products_by_modification": products_by_modification
    }

def generate_report(analysis: Dict[str, Any]) -> str:
    """
    Genera un informe legible a partir del análisis.
    
    Args:
        analysis: Resultados del análisis.
        
    Returns:
        Informe en formato de texto.
    """
    report = []
    report.append("=" * 80)
    report.append(f"INFORME DE PRODUCTOS MODIFICADOS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 80)
    report.append(f"Archivo de log: {analysis.get('log_file', 'desconocido')}")
    report.append(f"Total de productos modificados: {analysis.get('total_products', 0)}")
    report.append("")
    
    # Tipos de modificaciones
    report.append("TIPOS DE MODIFICACIONES")
    report.append("-" * 40)
    for mod_type, count in analysis.get("most_common_modifications", []):
        report.append(f"- {mod_type}: {count} productos ({round(count/analysis.get('total_products', 1)*100, 2)}%)")
    report.append("")
    
    # Resumen de descripcciones
    if analysis.get("description_summaries"):
        report.append("RESUMEN DE DESCRIPCIONES")
        report.append("-" * 40)
        report.append(f"Productos con descripciones resumidas: {len(analysis.get('description_summaries', []))}")
        report.append(f"Reducción media de longitud: {analysis.get('avg_description_reduction', 0)}%")
        report.append("")
        report.append("TOP 5 MAYORES REDUCCIONES:")
        
        # Ordenar por porcentaje de reducción
        top_reductions = sorted(
            analysis.get("description_summaries", []), 
            key=lambda x: x.get("reduction_percent", 0), 
            reverse=True
        )[:5]
        
        for item in top_reductions:
            report.append(f"- Producto {item.get('product_id')}: {item.get('original_length')} → {item.get('modified_length')} caracteres ({item.get('reduction_percent')}% reducción)")
        report.append("")
    
    # Productos con múltiples modificaciones
    if analysis.get("products_with_multiple_mods"):
        report.append("PRODUCTOS CON MÚLTIPLES MODIFICACIONES")
        report.append("-" * 40)
        for item in analysis.get("products_with_multiple_mods", [])[:10]:  # Mostrar solo los primeros 10
            report.append(f"- Producto {item.get('product_id')}: {', '.join(item.get('modifications', []))}")
        
        if len(analysis.get("products_with_multiple_mods", [])) > 10:
            report.append(f"  (y {len(analysis.get('products_with_multiple_mods', [])) - 10} más...)")
        report.append("")
    
    report.append("=" * 80)
    report.append("Fin del informe")
    report.append("=" * 80)
    
    return "\n".join(report)

if __name__ == "__main__":
    args = parse_args()
    
    # Determinar archivo de log a analizar
    log_file = args.log_file
    if not log_file:
        log_file = find_latest_log_file(args.log_dir)
        if not log_file:
            print("No se pudo encontrar un archivo de log para analizar.")
            exit(1)
    
    print(f"Analizando archivo de log: {log_file}")
    
    # Leer y analizar el archivo
    entries = read_log_file(log_file)
    
    if not entries:
        print("No se encontraron entradas en el archivo de log.")
        exit(1)
        
    print(f"Se encontraron {len(entries)} productos modificados.")
    
    # Analizar modificaciones
    analysis = analyze_modifications(entries)
    
    # Generar informe
    report = generate_report(analysis)
    
    # Guardar o mostrar el informe
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Informe guardado en: {args.output}")
    else:
        print("\n" + report)
