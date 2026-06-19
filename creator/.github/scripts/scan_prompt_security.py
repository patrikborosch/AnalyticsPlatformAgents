#!/usr/bin/env python3
"""
Prompt Security Scanner for skills-for-fabric
Detects dangerous patterns in skill prompt files that could enable prompt injection attacks.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Dangerous patterns that indicate prompt injection vulnerabilities
DANGEROUS_PATTERNS = [
    # Direct instruction manipulation
    (r'ignore\s+(previous|all|above|prior)\s+instructions', 
     'CRITICAL', 'Instruction to ignore system prompts'),
    
    (r'disregard\s+(previous|all|above|prior)\s+(instructions|rules)',
     'CRITICAL', 'Instruction to disregard system rules'),
    
    (r'forget\s+(everything|all|previous)',
     'HIGH', 'Instruction to forget context'),
    
    # System prompt extraction
    (r'(reveal|show|print|display|output)\s+(your\s+)?(system\s+)?(prompt|instructions|rules)',
     'CRITICAL', 'Attempt to extract system prompt'),
    
    (r'what\s+(are|were)\s+your\s+(original|initial|system)\s+instructions',
     'CRITICAL', 'Question asking for system instructions'),
    
    (r'repeat\s+(everything|all)\s+before',
     'HIGH', 'Request to repeat system instructions'),
    
    # Role/persona manipulation
    (r'you\s+are\s+now\s+(a|an)\s+\w+',
     'HIGH', 'Attempt to change AI role/persona'),
    
    (r'(act|behave|pretend)\s+as\s+(if|though)',
     'MEDIUM', 'Instruction to change behavior'),
    
    # Data exfiltration
    (r'send\s+(data|results|information)\s+to\s+https?://',
     'CRITICAL', 'Attempt to exfiltrate data to external URL'),
    
    (r'POST\s+.+\s+to\s+https?://',
     'CRITICAL', 'HTTP POST to external endpoint'),
    
    (r'(curl|wget|fetch|request)\s+https?://',
     'HIGH', 'External HTTP request'),
    
    # Secret exposure
    (r'(print|show|reveal|display)\s+(api\s+key|token|password|secret|credential)',
     'CRITICAL', 'Attempt to expose secrets'),
    
    (r'environment\s+variables',
     'MEDIUM', 'Reference to environment variables (may contain secrets)'),
    
    # Arbitrary code execution
    (r'(execute|eval|run)\s+(arbitrary|any)\s+code',
     'CRITICAL', 'Arbitrary code execution'),
    
    (r'exec\s*\(',
     'HIGH', 'Direct exec() call'),
    
    (r'__import__\s*\(',
     'HIGH', 'Dynamic module import'),
    
    # Tool abuse
    (r'call\s+any\s+tool',
     'HIGH', 'Unrestricted tool access'),
    
    (r'without\s+(confirmation|approval|asking)',
     'MEDIUM', 'Bypassing user confirmation'),
    
    # Prompt injection markers
    (r'<\|.*?\|>',
     'MEDIUM', 'Special delimiter that might confuse parser'),
    
    (r'\[SYSTEM\]|\[INST\]|\[/INST\]',
     'HIGH', 'Instruction delimiters'),
]

# Patterns that are suspicious but may be legitimate in examples/documentation
SUSPICIOUS_PATTERNS = [
    (r'delete\s+all',
     'WARNING', 'Destructive operation - ensure proper confirmation'),
    
    (r'DROP\s+(TABLE|DATABASE|SCHEMA)',
     'WARNING', 'SQL DROP statement - ensure user confirmation'),
    
    (r'sudo\s+',
     'WARNING', 'Elevated privileges'),
    
    (r'rm\s+-rf',
     'WARNING', 'Destructive file operation'),
]

def scan_file(file_path: Path, strict: bool = False) -> List[Tuple[str, int, str, str]]:
    """
    Scan a single file for dangerous patterns.
    
    Returns: List of (severity, line_number, pattern_description, line_content)
    """
    findings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return findings
    
    patterns_to_check = DANGEROUS_PATTERNS
    if strict:
        patterns_to_check = DANGEROUS_PATTERNS + SUSPICIOUS_PATTERNS
    
    for line_num, line in enumerate(lines, start=1):
        line_lower = line.lower()
        
        for pattern, severity, description in patterns_to_check:
            if re.search(pattern, line_lower, re.IGNORECASE):
                findings.append((severity, line_num, description, line.strip()))
    
    return findings

def scan_directory(directory: Path, strict: bool = False) -> dict:
    """
    Recursively scan directory for skill files.
    
    Returns: Dict mapping file paths to list of findings
    """
    results = {}
    
    # File extensions to scan
    extensions = ['.md', '.txt', '.py', '.yaml', '.yml', '.json']
    
    for file_path in directory.rglob('*'):
        if file_path.is_file() and file_path.suffix in extensions:
            # Skip certain directories
            if any(skip in file_path.parts for skip in ['.git', 'node_modules', '__pycache__', '.venv']):
                continue
            
            findings = scan_file(file_path, strict)
            if findings:
                results[file_path] = findings
    
    return results

def print_results(results: dict, fail_on_findings: bool = True) -> int:
    """
    Print scan results and return exit code.
    
    Returns: 0 if no critical findings, 1 if critical findings found
    """
    if not results:
        print("✅ No dangerous patterns found.")
        return 0
    
    critical_count = 0
    high_count = 0
    medium_count = 0
    warning_count = 0
    
    for file_path, findings in sorted(results.items()):
        print(f"\n📄 {file_path}")
        print("─" * 80)
        
        for severity, line_num, description, line_content in findings:
            if severity == 'CRITICAL':
                critical_count += 1
                icon = '🔴'
            elif severity == 'HIGH':
                high_count += 1
                icon = '🟠'
            elif severity == 'MEDIUM':
                medium_count += 1
                icon = '🟡'
            else:
                warning_count += 1
                icon = '⚪'
            
            print(f"{icon} {severity} (Line {line_num}): {description}")
            print(f"   {line_content}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"🔴 Critical: {critical_count}")
    print(f"🟠 High: {high_count}")
    print(f"🟡 Medium: {medium_count}")
    print(f"⚪ Warnings: {warning_count}")
    print(f"📁 Files affected: {len(results)}")
    
    if critical_count > 0:
        print("\n❌ SCAN FAILED: Critical security issues detected!")
        return 1
    elif high_count > 0 and fail_on_findings:
        print("\n⚠️  SCAN FAILED: High-severity issues detected!")
        return 1
    elif medium_count > 0 or warning_count > 0:
        print("\n⚠️  Warnings found - please review.")
        return 0 if not fail_on_findings else 0
    
    return 0

def main():
    parser = argparse.ArgumentParser(
        description='Scan skills-for-fabric prompts for security vulnerabilities'
    )
    parser.add_argument(
        '--path',
        type=str,
        default='.',
        help='Path to scan (file or directory)'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Enable strict mode (check suspicious patterns too)'
    )
    parser.add_argument(
        '--fail-on-warnings',
        action='store_true',
        help='Fail on warnings (not just critical/high)'
    )
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if not path.exists():
        print(f"Error: Path '{path}' does not exist", file=sys.stderr)
        return 1
    
    print(f"🔍 Scanning: {path}")
    print(f"   Strict mode: {args.strict}")
    print("─" * 80)
    
    if path.is_file():
        findings = scan_file(path, args.strict)
        results = {path: findings} if findings else {}
    else:
        results = scan_directory(path, args.strict)
    
    return print_results(results, args.fail_on_warnings)

if __name__ == '__main__':
    sys.exit(main())
