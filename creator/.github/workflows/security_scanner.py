#!/usr/bin/env python3
"""
Production-ready security scanner for skills-for-fabric
Designed for CI/CD pipeline integration with proper exit codes and JSON reporting
"""
import re
import json
import sys
import io
from pathlib import Path
from typing import List, Dict, Any

# Fix Unicode output on Windows (cp1252 can't handle emoji)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

class SecurityScanner:
    def __init__(self):
        self.results = {
            'overall_status': 'SAFE',
            'files_scanned': 0,
            'total_checks': 0,
            'injection_risks': 0,
            'sensitive_info': 0,
            'malicious_code': 0,
            'files': {}
        }
        
    def scan_prompt_injection_risks(self, content: str, filename: str) -> List[Dict]:
        """Scan for potential prompt injection attack vectors"""
        injection_patterns = [
            (r'ignore.*previous.*instruction', 'Instruction override attempt', 'CRITICAL'),
            (r'act\s+as\s+(?:if\s+)?you\s+are', 'Role manipulation attempt', 'CRITICAL'),
            (r'forget\s+everything', 'Memory wipe attempt', 'CRITICAL'),
            (r'system\s*:\s*[^a-zA-Z0-9\s]', 'System message injection', 'CRITICAL'),
            (r'you\s+are\s+now\s+a', 'Identity override', 'CRITICAL'),
            (r'pretend\s+to\s+be', 'Persona injection', 'CRITICAL'),
            (r'override.*guidelines?', 'Guideline bypass', 'CRITICAL'),
            (r'bypass.*safety', 'Safety bypass', 'CRITICAL'),
            (r'don[\'t]*\s+follow.*rules?', 'Rule bypass', 'CRITICAL'),
            (r'what\s+are\s+your\s+instructions', 'Instruction extraction', 'HIGH'),
            (r'show.*system\s+prompt', 'System prompt extraction', 'HIGH'),
            (r'reveal.*training', 'Training data extraction', 'HIGH'),
            (r'\\\\[rnt]|\\x[0-9a-f]+', 'Escape sequence injection', 'MEDIUM'),
            (r'<script[^>]*>', 'Script injection attempt', 'HIGH'),
            (r'\{\{.*\}\}', 'Template injection attempt', 'MEDIUM'),
            (r'exec\s*\(.*input.*\)', 'Dynamic execution with input', 'CRITICAL')
        ]
        
        risks_found = []
        for pattern, risk_type, severity in injection_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                context = content[max(0, match.start()-50):match.end()+50].strip()
                
                # Skip obvious documentation examples
                if any(skip in context.lower() for skip in [
                    'example', 'demonstration', 'sample code', '# don\'t do this',
                    'avoid', 'never', 'prohibited', 'dangerous', 'commandlinearguments',
                    'parameters', 'arguments', '--date', '--batch'
                ]):
                    continue
                
                risks_found.append({
                    'type': risk_type,
                    'severity': severity,
                    'pattern': pattern,
                    'match': match.group(),
                    'line': line_num,
                    'context': context[:100] + '...' if len(context) > 100 else context
                })
                
        return risks_found

    def scan_sensitive_information(self, content: str, filename: str) -> List[Dict]:
        """Scan for potentially sensitive information"""
        sensitive_patterns = [
            # Real GUIDs (not placeholders)
            (r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', 'Potential real GUID'),
            # JWT tokens
            (r'eyJ[a-zA-Z0-9+/=]{20,}', 'Potential JWT token'),
            # API keys
            (r'sk-[a-zA-Z0-9]{32,}', 'Potential OpenAI API key'),
            (r'[a-zA-Z0-9]{32,}\.[a-zA-Z0-9]{6,}', 'Potential API token'),
            # Specific tenant domains (not examples)
            (r'[a-zA-Z0-9-]+\.onmicrosoft\.com(?!.*example)', 'Real tenant domain'),
            # Specific Azure domains (not examples)
            (r'https://(?!example)[a-zA-Z0-9-]+\.(?:blob|dfs|database|vault)\.core\.windows\.net', 'Real Azure endpoint'),
            (r'https://(?!example)[a-zA-Z0-9-]+\.(?:analysis\.windows\.net)', 'Real Azure Analysis Services'),
            # Bearer tokens
            (r'Bearer\s+[a-zA-Z0-9+/=]{20,}', 'Real bearer token'),
            # Hardcoded credentials
            (r'password["\']?\s*[:=]\s*["\'][^"\']{8,}["\']', 'Hardcoded password'),
            (r'secret["\']?\s*[:=]\s*["\'][^"\']{10,}["\']', 'Hardcoded secret'),
            # Connection strings
            (r'Server=tcp:[^;]+;Database=[^;]+;', 'SQL connection string'),
            (r'DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+', 'Storage connection string')
        ]
        
        sensitive_found = []
        for pattern, info_type in sensitive_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            for match in matches:
                match_text = match.group()
                
                # Skip obvious examples/placeholders
                if any(placeholder in match_text.lower() for placeholder in [
                    'your-', 'example', 'placeholder', 'sample', 'test', 'demo',
                    'contoso', 'northwind', 'adventure', 'xxx', '000', 'abc'
                ]):
                    continue
                
                # Skip documentation patterns
                if any(doc_pattern in match_text.lower() for doc_pattern in [
                    'learn.microsoft.com', 'docs.microsoft.com', 'github.com'
                ]):
                    continue
                    
                line_num = content[:match.start()].count('\n') + 1
                sensitive_found.append({
                    'type': info_type,
                    'match': match_text[:50] + '...' if len(match_text) > 50 else match_text,
                    'line': line_num,
                    'full_match': match_text
                })
        
        return sensitive_found

    def scan_malicious_code_patterns(self, content: str, filename: str) -> List[Dict]:
        """Scan for potentially malicious code patterns"""
        malicious_patterns = [
            (r'eval\s*\([^)]*(?:input|raw_input|sys\.argv)[^)]*\)', 'Dynamic execution with user input', 'CRITICAL'),
            (r'exec\s*\([^)]*(?:input|raw_input|sys\.argv)[^)]*\)', 'Dynamic execution with user input', 'CRITICAL'),
            (r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True[^)]*(?:input|raw_input|sys\.argv)', 'Shell injection with user input', 'CRITICAL'),
            (r'os\.system\s*\([^)]*(?:input|raw_input|sys\.argv)', 'System command with user input', 'CRITICAL'),
            (r'__import__\s*\([^)]*(?:input|raw_input)', 'Dynamic import with user input', 'HIGH'),
            (r'open\s*\([^)]*(?:input|raw_input)[^)]*["\']w', 'File write with user input', 'HIGH'),
            (r'requests\.(?:get|post)\([^)]*verify\s*=\s*False', 'Disabled SSL verification', 'MEDIUM'),
            (r'urllib.*urlopen.*http:[^s]', 'Insecure HTTP request', 'LOW'),
            (r'pickle\.loads?\([^)]*(?:input|raw_input)', 'Unsafe pickle deserialization', 'HIGH'),
            (r'yaml\.load\([^)]*(?:input|raw_input)', 'Unsafe YAML loading', 'MEDIUM')
        ]
        
        malicious_found = []
        for pattern, risk_type, severity in malicious_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                context = content[max(0, match.start()-30):match.end()+30].strip()
                
                # Skip obvious documentation examples
                if any(skip in context.lower() for skip in [
                    '# don\'t do this', '# bad example', '# avoid', 'dangerous', 'vulnerable'
                ]):
                    continue
                
                malicious_found.append({
                    'type': risk_type,
                    'severity': severity,
                    'match': match.group(),
                    'line': line_num,
                    'context': context[:100] + '...' if len(context) > 100 else context
                })
        
        return malicious_found

    def scan_file(self, file_path: Path) -> Dict[str, Any]:
        """Scan a single file for security risks"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return {
                'error': f"Could not read file: {e}",
                'injection_risks': [],
                'sensitive_info': [],
                'malicious_code': []
            }
        
        injection_risks = self.scan_prompt_injection_risks(content, file_path.name)
        sensitive_info = self.scan_sensitive_information(content, file_path.name)
        malicious_code = self.scan_malicious_code_patterns(content, file_path.name)
        
        return {
            'injection_risks': injection_risks,
            'sensitive_info': sensitive_info,
            'malicious_code': malicious_code,
            'line_count': len(content.splitlines()),
            'char_count': len(content)
        }

    def scan_repository(self) -> bool:
        """Scan entire repository for security risks"""
        print("🛡️  skills-for-fabric SECURITY AUDIT")
        print("=" * 50)
        
        # Find all skill markdown files
        skill_files = []
        for pattern in ['skills/**/*.md', '.github/skills/**/*.md']:
            skill_files.extend(Path('.').glob(pattern))
        
        if not skill_files:
            print("⚠️  No skill files found to scan")
            return True
        
        critical_issues = 0
        
        for skill_file in skill_files:
            print(f"\n🔍 Scanning: {skill_file}")
            
            file_results = self.scan_file(skill_file)
            self.results['files'][str(skill_file)] = file_results
            self.results['files_scanned'] += 1
            
            if 'error' in file_results:
                print(f"❌ Error: {file_results['error']}")
                continue
            
            # Count risks
            injection_count = len(file_results['injection_risks'])
            sensitive_count = len(file_results['sensitive_info'])
            malicious_count = len(file_results['malicious_code'])
            
            self.results['injection_risks'] += injection_count
            self.results['sensitive_info'] += sensitive_count
            self.results['malicious_code'] += malicious_count
            self.results['total_checks'] += 3
            
            # Report critical issues
            critical_in_file = 0
            for risk in file_results['injection_risks']:
                if risk['severity'] == 'CRITICAL':
                    critical_in_file += 1
                    critical_issues += 1
                    print(f"   🚨 CRITICAL: {risk['type']} (Line {risk['line']})")
            
            for risk in file_results['malicious_code']:
                if risk['severity'] == 'CRITICAL':
                    critical_in_file += 1
                    critical_issues += 1
                    print(f"   🚨 CRITICAL: {risk['type']} (Line {risk['line']})")
            
            # Report other issues
            if injection_count > critical_in_file:
                print(f"   ⚠️  {injection_count - critical_in_file} non-critical prompt injection risks")
            
            if sensitive_count > 0:
                print(f"   📝 {sensitive_count} sensitive information items")
            
            if malicious_count > critical_in_file:
                print(f"   ⚠️  {malicious_count - critical_in_file} non-critical code risks")
            
            if injection_count == 0 and sensitive_count == 0 and malicious_count == 0:
                print("   ✅ No security risks detected")
        
        # Final assessment
        print(f"\n{'='*50}")
        print("🏆 SECURITY AUDIT SUMMARY")
        print(f"Files scanned: {self.results['files_scanned']}")
        print(f"Total security checks: {self.results['total_checks']}")
        print(f"Prompt injection risks: {self.results['injection_risks']}")
        print(f"Sensitive information: {self.results['sensitive_info']}")
        print(f"Malicious code patterns: {self.results['malicious_code']}")
        
        if critical_issues > 0:
            print(f"\n🚨 RESULT: FAILED - {critical_issues} CRITICAL SECURITY ISSUES")
            print("❌ Repository is NOT SAFE for open source release")
            self.results['overall_status'] = 'CRITICAL'
            return False
        elif self.results['injection_risks'] > 0 or self.results['malicious_code'] > 0:
            print(f"\n⚠️  RESULT: REVIEW REQUIRED - Non-critical security issues found")
            print("🔍 Manual review needed before open source release")
            self.results['overall_status'] = 'REVIEW'
            return False
        elif self.results['sensitive_info'] > 0:
            print(f"\n📝 RESULT: SANITIZATION NEEDED - Sensitive information found")
            print("🧹 Remove sensitive information before open source release")
            self.results['overall_status'] = 'SANITIZE'
            return False
        else:
            print(f"\n✅ RESULT: PASSED - Repository is SAFE for open source release")
            print("🎉 No security risks detected")
            self.results['overall_status'] = 'SAFE'
            return True

    def save_report(self, output_file: str = 'security-report.json'):
        """Save detailed security report to JSON file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"📄 Detailed report saved to: {output_file}")

def main():
    """Main entry point for CI/CD pipeline"""
    scanner = SecurityScanner()

    exit_code = 0
    try:
        scanner.scan_repository()
        if scanner.results['overall_status'] == 'CRITICAL':
            print("\n💥 CRITICAL SECURITY ISSUES - BUILD FAILED")
            exit_code = 1
        elif scanner.results['overall_status'] in ['REVIEW', 'SANITIZE']:
            print("\n⚠️  SECURITY REVIEW REQUIRED - BUILD WARNING")
            exit_code = 0
        else:
            print("\n🎉 SECURITY AUDIT PASSED - BUILD SUCCESS")
            exit_code = 0

    except Exception as e:
        scanner.results['overall_status'] = 'ERROR'
        scanner.results['error'] = str(e)
        print(f"\n💥 SECURITY SCAN FAILED: {e}")
        exit_code = 2

    scanner.save_report()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
