#!/usr/bin/env python3
"""
Skill Quality Checker for skills-for-fabric
Validates skill files for semantic disambiguation, structural compliance, and content quality.
"""
import re
import json
import sys
import io
from pathlib import Path
from typing import Dict, Any


def _configure_windows_unicode_stdout():
    """Wrap stdout/stderr in UTF-8 TextIOWrappers on Windows so emoji print.

    Side-effecting and unsafe under pytest's stdout capture, so we only run it
    when the script is executed directly (``main()``) and never on import.
    """
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Optional: requests for link validation
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Optional: tiktoken for accurate token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# quality_checker.py lives under .github/workflows/, so parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skill_validation import (
    analyze_common_infra_compliance,
    analyze_naming_convention,
    analyze_structural_compliance,
    build_similarity_matrix as build_shared_similarity_matrix,
    detect_encoding_corruption,
    find_ambiguous_triggers,
    find_duplicate_triggers,
    find_semantic_conflicts,
    find_trigger_overlap,
    load_skill_document,
)


class QualityChecker:
    # Token thresholds for recommendations
    TOKEN_THRESHOLD_WARNING = 8000    # Warn if skill exceeds this
    TOKEN_THRESHOLD_CRITICAL = 15000  # Critical if skill exceeds this
    TOKEN_THRESHOLD_TOTAL = 50000     # Warn if total exceeds this
    
    def __init__(self):
        self.results = {
            'overall_status': 'PASSED',
            'files_scanned': 0,
            'critical_count': 0,
            'warning_count': 0,
            'semantic_conflicts': [],
            'duplicate_triggers': [],
            'ambiguous_triggers': [],  # New: semantically similar triggers across skills
            'trigger_overlaps': [],    # Sensei-inspired: Triggers: field set overlap between skill pairs
            'broken_references': [],
            'common_infra_issues': [],
            'structural_issues': [],
            'content_warnings': [],
            'skills': {},
            'token_costs': {},        # skill_name -> {total, files: [{path, tokens}]}
            'recommendations': []     # List of actionable recommendations
        }
        self.all_skills: Dict[str, Dict] = {}  # skill_name -> {description, triggers, path}
        self._tiktoken_encoder = None
    
    def _get_encoder(self):
        """Get tiktoken encoder, lazy-loaded."""
        if self._tiktoken_encoder is None and TIKTOKEN_AVAILABLE:
            self._tiktoken_encoder = tiktoken.get_encoding('cl100k_base')
        return self._tiktoken_encoder
    
    def count_tokens(self, content: str) -> int:
        """Count tokens in content using tiktoken or fallback estimation."""
        encoder = self._get_encoder()
        if encoder:
            return len(encoder.encode(content))
        else:
            # Fallback: estimate ~4 chars per token
            return len(content) // 4
    
    def check_semantic_disambiguation(self):
        """Check for overlapping or conflicting skill descriptions."""
        conflicts = find_semantic_conflicts(self.all_skills)
        self.results['semantic_conflicts'].extend(conflicts)
        self.results['critical_count'] += len(conflicts)
    
    def build_similarity_matrix(self):
        """Build a Jaccard similarity matrix between all skill descriptions."""
        matrix = build_shared_similarity_matrix(self.all_skills)
        if matrix:
            self.results['similarity_matrix'] = matrix
    
    def check_trigger_uniqueness(self):
        """Check for duplicate trigger phrases across skills."""
        duplicates = find_duplicate_triggers(self.all_skills)
        self.results['duplicate_triggers'].extend(duplicates)
        self.results['critical_count'] += len(duplicates)
    
    def check_semantic_trigger_ambiguity(self):
        """Check for semantically similar triggers that could cause routing confusion."""
        ambiguous = find_ambiguous_triggers(self.all_skills)
        self.results['ambiguous_triggers'].extend(ambiguous)
        self.results['warning_count'] += len(ambiguous)

    def check_trigger_overlap(self):
        """Sensei-inspired heuristic: report skill pairs whose ``Triggers:`` field
        token sets overlap by more than the threshold.

        Stored under a dedicated ``trigger_overlaps`` results key (not the
        CRITICAL-only ``semantic_conflicts`` array) so the existing
        recommendations logic keeps its severity contract. WARNING severity:
        never blocks merge."""
        overlaps = find_trigger_overlap(self.all_skills)
        self.results['trigger_overlaps'].extend(overlaps)
        self.results['warning_count'] += len(overlaps)

    def check_cross_references(self, content: str, skill_path: Path, skill_name: str):
        """Check that relative paths in markdown links exist."""
        # Find markdown links: [text](path)
        links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', content)
        seen_paths = set()
        
        for text, link_path in links:
            # Skip external URLs
            if link_path.startswith('http://') or link_path.startswith('https://'):
                continue
            
            # Skip anchors
            if link_path.startswith('#'):
                continue
            
            # Remove anchor from path
            link_path_clean = link_path.split('#')[0]
            
            if not link_path_clean:
                continue
            
            # Skip duplicates within same file
            if link_path_clean in seen_paths:
                continue
            seen_paths.add(link_path_clean)
            
            # Resolve relative path
            base_dir = skill_path.parent
            resolved = (base_dir / link_path_clean).resolve()
            
            if not resolved.exists():
                self.results['broken_references'].append({
                    'skill': skill_name,
                    'path': link_path_clean,
                    'expected': str(resolved)
                })
                self.results['critical_count'] += 1
    
    def check_structural_compliance(self, content: str, frontmatter: Dict, skill_name: str) -> Dict:
        """Check structural requirements for skill files."""
        checks = analyze_structural_compliance(content, frontmatter, skill_name)
        untagged = checks['untagged_code_blocks']
        
        # Report issues
        if not checks['has_frontmatter']:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL',
                'message': 'Missing YAML frontmatter'
            })
            self.results['critical_count'] += 1
        
        if checks['has_frontmatter'] and not checks['has_name']:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL', 
                'message': 'Missing "name" field in frontmatter'
            })
            self.results['critical_count'] += 1
        
        if checks['has_frontmatter'] and not checks['has_description']:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL',
                'message': 'Missing "description" field in frontmatter'
            })
            self.results['critical_count'] += 1
        
        if not checks['has_update_notice'] and skill_name != 'check-updates':
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL',
                'message': 'Missing update check notice blockquote'
            })
            self.results['critical_count'] += 1
        
        if not checks['has_must_prefer_avoid']:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'WARNING',
                'message': 'Missing Must/Prefer/Avoid or Gotchas/Rules sections'
            })
            self.results['warning_count'] += 1
        
        if not checks['has_examples']:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'WARNING',
                'message': 'Missing examples section or code examples'
            })
            self.results['warning_count'] += 1

        # Skill routers index on the explicit ``Triggers:`` field. The
        # ``check-updates`` utility skill is exempt because its description is
        # intentionally lean.
        if not checks.get('has_triggers_field') and skill_name != 'check-updates':
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'WARNING',
                'message': (
                    "Description missing explicit 'Triggers:' field -- "
                    "skill routers index on this; add a comma-separated trigger phrase list."
                )
            })
            self.results['warning_count'] += 1

        if untagged > 0:
            self.results['content_warnings'].append({
                'skill': skill_name,
                'message': f'{untagged} code block(s) missing language tag'
            })
            self.results['warning_count'] += 1
        
        return checks

    def check_common_infra_compliance(self, content: str, skill_name: str) -> Dict[str, Any]:
        """Check that shared auth/tooling guidance points back to common docs."""
        checks = analyze_common_infra_compliance(content)

        for issue in checks['issues']:
            self.results['common_infra_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL',
                'message': issue['message'],
                'rule': issue['rule'],
                'missing_references': issue['missing_references'],
            })
            self.results['critical_count'] += 1

        return checks

    def check_encoding_integrity(self, skill_path: Path, skill_name: str) -> list[Dict[str, Any]]:
        """Check all markdown files in a skill folder for mojibake or decode failures."""
        issues: list[Dict[str, Any]] = []
        skill_dir = skill_path.parent

        for markdown_path in sorted(skill_dir.rglob('*.md')):
            relative_path = markdown_path.relative_to(skill_dir)
            try:
                markdown_content = markdown_path.read_text(encoding='utf-8')
            except UnicodeDecodeError as exc:
                issues.append({
                    'skill': skill_name,
                    'severity': 'CRITICAL',
                    'kind': 'invalid_utf8',
                    'path': str(relative_path),
                    'message': f'Markdown file `{relative_path}` is not valid UTF-8: {exc.reason}',
                })
                continue

            markers = detect_encoding_corruption(markdown_content)
            if markers:
                marker_preview = ', '.join(f'`{marker}`' for marker in markers)
                issues.append({
                    'skill': skill_name,
                    'severity': 'CRITICAL',
                    'kind': 'mojibake',
                    'path': str(relative_path),
                    'message': (
                        f'Markdown file `{relative_path}` contains suspect encoding corruption markers: '
                        f'{marker_preview}'
                    ),
                })

        for issue in issues:
            self.results['structural_issues'].append(issue)
            self.results['critical_count'] += 1

        return issues
    
    def check_description_length(self, description: str, skill_name: str):
        """Check description length limits."""
        desc_len = len(description)
        
        # Critical: description exceeds 1023 characters (blocks check-in)
        if desc_len > 1023:
            self.results['structural_issues'].append({
                'skill': skill_name,
                'severity': 'CRITICAL',
                'message': f'Description exceeds 1023 characters ({desc_len} chars) - must shorten to allow check-in'
            })
            self.results['critical_count'] += 1
        # Warning: description approaching limit (>= 900 characters)
        elif desc_len >= 900:
            self.results['content_warnings'].append({
                'skill': skill_name,
                'message': f'Description approaching limit ({desc_len}/1023 chars) - consider shortening'
            })
            self.results['warning_count'] += 1
    
    def check_description_quality(self, description: str, skill_name: str):
        """Check description quality for discoverability."""
        issues = []
        
        # Check mentions specific technologies
        tech_keywords = ['sql', 't-sql', 'python', 'powershell', 'bash', 'cli', 
                        'rest', 'api', 'sdk', 'fabric', 'warehouse', 'lakehouse',
                        'spark', 'notebook', 'pipeline', 'dataflow']
        desc_lower = description.lower()
        has_tech = any(tech in desc_lower for tech in tech_keywords)
        if not has_tech:
            issues.append('Description should mention specific technologies')
        
        # Check has trigger phrases
        if 'trigger' not in desc_lower and 'when' not in desc_lower and 'use' not in desc_lower:
            issues.append('Description should include trigger phrases or usage context')
        
        for issue in issues:
            self.results['content_warnings'].append({
                'skill': skill_name,
                'message': issue
            })
            self.results['warning_count'] += 1

    def check_naming_convention(self, skill_name: str):
        """Check skill naming follows conventions."""
        naming = analyze_naming_convention(skill_name)
        if not naming['matches_recommended_pattern']:
            self.results['content_warnings'].append({
                'skill': skill_name,
                'message': f'Consider naming pattern: {{endpoint}}-authoring-{{access}}, {{endpoint}}-consumption-{{access}}, or {{endpoint}}-operations-{{access}}'
            })
            self.results['warning_count'] += 1
    
    def check_external_links(self, content: str, skill_name: str):
        """Validate external URLs are accessible (rate-limited)."""
        if not REQUESTS_AVAILABLE:
            return
        
        # Find external URLs
        urls = re.findall(r'https?://[^\s\)>\]]+', content)
        
        # Sample max 5 links to avoid slowdown
        urls = list(set(urls))[:5]
        
        for url in urls:
            # Skip GitHub raw content (often requires auth)
            if 'raw.githubusercontent.com' in url:
                continue
            
            try:
                response = requests.head(url, timeout=5, allow_redirects=True)
                if response.status_code >= 400:
                    self.results['content_warnings'].append({
                        'skill': skill_name,
                        'message': f'Link may be broken (HTTP {response.status_code}): {url[:60]}...'
                    })
                    self.results['warning_count'] += 1
            except requests.RequestException:
                # Network issues, skip silently
                pass
    
    def check_content_quality(self, content: str, skill_name: str):
        """Check content quality metrics."""
        # Use accurate token counting
        estimated_tokens = self.count_tokens(content)
        
        # Flag very large files
        if estimated_tokens > 10000:
            self.results['content_warnings'].append({
                'skill': skill_name,
                'message': f'Large file (~{estimated_tokens} tokens) - consider splitting into focused skills'
            })
            self.results['warning_count'] += 1
    
    def scan_skill(self, skill_path: Path) -> Dict[str, Any]:
        """Scan a single skill file."""
        skill_name = skill_path.parent.name
        checks: Dict[str, Any] = {}
        encoding_issues = self.check_encoding_integrity(skill_path, skill_name)
        checks['encoding'] = encoding_issues

        if any(
            issue.get('kind') == 'invalid_utf8' and issue.get('path') == skill_path.name
            for issue in encoding_issues
        ):
            checks['error'] = f'Could not read file: `{skill_path.name}` is not valid UTF-8.'
            return checks
        
        try:
            skill_document = load_skill_document(skill_path)
        except Exception as e:
            checks['error'] = f'Could not read file: {e}'
            return checks
        
        content = skill_document['content']
        frontmatter = skill_document['frontmatter']
        
        # Store skill metadata for cross-skill checks
        self.all_skills[skill_name] = {
            'description': skill_document['description'],
            'triggers': skill_document['triggers'],
            'path': str(skill_path)
        }
        description = self.all_skills[skill_name]['description']
        
        # Run structural checks
        checks.update(self.check_structural_compliance(content, frontmatter, skill_name))
        checks['common_infra'] = self.check_common_infra_compliance(content, skill_name)

        # Run cross-reference checks
        self.check_cross_references(content, skill_path, skill_name)
        
        # Run description quality checks
        if description:
            self.check_description_length(description, skill_name)
            self.check_description_quality(description, skill_name)
        
        # Run naming convention checks
        self.check_naming_convention(skill_name)
        
        # Run content quality checks
        self.check_content_quality(content, skill_name)
        
        # Run external link validation (rate-limited)
        self.check_external_links(content, skill_name)
        
        # Calculate token costs for all files in skill
        self.calculate_token_costs(skill_path, skill_name)
        
        return checks
    
    def calculate_token_costs(self, skill_path: Path, skill_name: str):
        """Calculate token costs for all files in a skill directory."""
        skill_dir = skill_path.parent
        total_tokens = 0
        file_costs = []
        try:
            with open(skill_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            tokens = self.count_tokens(content)
            total_tokens += tokens
            rel_path = str(skill_path.relative_to(skill_dir))
            file_costs.append({'path': rel_path, 'tokens': tokens})
        except Exception:
            pass
        
        # Sort by tokens descending
        file_costs.sort(key=lambda x: -x['tokens'])
        
        self.results['token_costs'][skill_name] = {
            'total': total_tokens,
            'files': file_costs
        }
        
        return total_tokens
    
    def generate_recommendations(self):
        """Generate actionable recommendations based on all checks."""
        recommendations = []
        
        # Token cost recommendations
        total_tokens = sum(tc['total'] for tc in self.results['token_costs'].values())
        
        for skill_name, token_data in self.results['token_costs'].items():
            skill_tokens = token_data['total']
            
            if skill_tokens > self.TOKEN_THRESHOLD_CRITICAL:
                recommendations.append({
                    'severity': 'CRITICAL',
                    'skill': skill_name,
                    'category': 'token_cost',
                    'message': f'Skill uses {skill_tokens:,} tokens (>{self.TOKEN_THRESHOLD_CRITICAL:,}) - strongly consider splitting into smaller skills or using resource routing',
                    'impact': 'High token costs increase latency and API costs'
                })
            elif skill_tokens > self.TOKEN_THRESHOLD_WARNING:
                recommendations.append({
                    'severity': 'WARNING',
                    'skill': skill_name,
                    'category': 'token_cost',
                    'message': f'Skill uses {skill_tokens:,} tokens (>{self.TOKEN_THRESHOLD_WARNING:,}) - consider splitting or trimming',
                    'impact': 'Moderate token costs may impact performance'
                })
        
        if total_tokens > self.TOKEN_THRESHOLD_TOTAL:
            recommendations.append({
                'severity': 'WARNING',
                'skill': None,
                'category': 'token_cost',
                'message': f'Total token cost across all skills is {total_tokens:,} (>{self.TOKEN_THRESHOLD_TOTAL:,})',
                'impact': 'High aggregate costs if multiple skills are loaded'
            })
        
        # Ambiguous trigger recommendations
        for amb in self.results['ambiguous_triggers']:
            skills_list = ', '.join([s['skill'] for s in amb['skills']])
            recommendations.append({
                'severity': 'WARNING',
                'skill': None,
                'category': 'disambiguation',
                'message': f'Trigger "{amb["trigger_phrase"]}" matches multiple skills: {skills_list}',
                'impact': 'May cause incorrect skill routing'
            })
        
        # Description length recommendations
        for issue in self.results['structural_issues']:
            if 'description' in issue.get('message', '').lower() and 'exceeds' in issue.get('message', '').lower():
                recommendations.append({
                    'severity': 'CRITICAL',
                    'skill': issue['skill'],
                    'category': 'description',
                    'message': issue['message'],
                    'impact': 'Blocks plugin check-in'
                })
        
        # Similarity recommendations
        for conflict in self.results['semantic_conflicts']:
            recommendations.append({
                'severity': 'CRITICAL',
                'skill': f"{conflict['skill1']} & {conflict['skill2']}",
                'category': 'similarity',
                'message': f"{conflict['similarity']*100:.0f}% description similarity - differentiate these skills",
                'impact': 'High similarity causes ambiguous routing'
            })

        # Sensei-inspired: trigger-set overlap pairs (WARNING; never block).
        for overlap in self.results.get('trigger_overlaps', []):
            recommendations.append({
                'severity': 'WARNING',
                'skill': f"{overlap['skill1']} & {overlap['skill2']}",
                'category': 'trigger_overlap',
                'message': (
                    f"{overlap['overlap_pct']}% trigger-set overlap "
                    f"(shared: {', '.join(overlap['shared_triggers'][:3])})"
                ),
                'impact': 'May cause routing collisions; review whether overlap is intentional'
            })

        for issue in self.results['common_infra_issues']:
            recommendations.append({
                'severity': 'CRITICAL',
                'skill': issue['skill'],
                'category': 'common_infra',
                'message': issue['message'],
                'impact': 'Shared auth and tooling guidance will drift unless it is rooted in common/'
            })
        
        self.results['recommendations'] = recommendations
        return recommendations
    
    def scan_repository(self) -> bool:
        """Scan all skill files in the repository."""
        print("🔍 skills-for-fabric QUALITY CHECK")
        print("=" * 50)
        
        # Find skill files (only in skills/, exclude graveyard)
        skill_files = []
        for skill_md in Path('skills').glob('**/SKILL.md'):
            # Skip graveyard
            if 'graveyard' in str(skill_md):
                continue
            skill_files.append(skill_md)
        
        if not skill_files:
            print("⚠️  No skill files found to scan")
            return True
        
        # First pass: scan all skills
        for skill_path in skill_files:
            skill_name = skill_path.parent.name
            print(f"\n📄 Scanning: {skill_name}")
            
            critical_before = self.results['critical_count']
            checks = self.scan_skill(skill_path)
            self.results['files_scanned'] += 1
            self.results['skills'][skill_name] = checks
            
            if 'error' in checks:
                print(f"   ❌ Error: {checks['error']}")
                if self.results['critical_count'] == critical_before:
                    self.results['structural_issues'].append({
                        'skill': skill_name,
                        'severity': 'CRITICAL',
                        'message': checks['error'],
                    })
                    self.results['critical_count'] += 1
                continue
        
        # Second pass: cross-skill checks
        print("\n🔀 Running cross-skill analysis...")
        self.check_semantic_disambiguation()
        self.check_trigger_uniqueness()
        self.check_semantic_trigger_ambiguity()
        self.check_trigger_overlap()
        self.build_similarity_matrix()
        
        # Determine overall status
        if self.results['critical_count'] > 0:
            self.results['overall_status'] = 'CRITICAL'
        elif self.results['warning_count'] > 0:
            self.results['overall_status'] = 'WARNING'
        else:
            self.results['overall_status'] = 'PASSED'
        
        # Print summary
        print(f"\n{'='*50}")
        print("📊 QUALITY CHECK SUMMARY")
        print(f"Files scanned: {self.results['files_scanned']}")
        print(f"Critical issues: {self.results['critical_count']}")
        print(f"Warnings: {self.results['warning_count']}")
        
        if self.results['semantic_conflicts']:
            print(f"\n🔀 Semantic conflicts: {len(self.results['semantic_conflicts'])}")
            for conflict in self.results['semantic_conflicts']:
                print(f"   - {conflict['skill1']} <-> {conflict['skill2']}: {conflict['reason']}")
        
        if self.results['duplicate_triggers']:
            print(f"\n🎯 Duplicate triggers: {len(self.results['duplicate_triggers'])}")
            for dup in self.results['duplicate_triggers']:
                print(f"   - \"{dup['trigger']}\" used by: {', '.join(dup['skills'])}")
        
        if self.results['ambiguous_triggers']:
            print(f"\n⚠️  Semantically ambiguous triggers: {len(self.results['ambiguous_triggers'])}")
            print(f"\n   | {'Trigger Phrase':<20} | {'Matches These Skills':<50} | Ambiguity |")
            print(f"   |{'-'*22}|{'-'*52}|{'-'*11}|")
            for amb in self.results['ambiguous_triggers']:
                skills_str = ', '.join([s['skill'] for s in amb['skills']])
                print(f"   | {amb['trigger_phrase']:<20} | {skills_str:<50} | {len(amb['skills'])} skills |")

        if self.results['trigger_overlaps']:
            print(f"\n⚠️  Trigger-set overlaps (Sensei heuristic): {len(self.results['trigger_overlaps'])}")
            for overlap in self.results['trigger_overlaps']:
                shared = ', '.join(f'"{t}"' for t in overlap['shared_triggers'][:3])
                more = '' if len(overlap['shared_triggers']) <= 3 else f' (+{len(overlap["shared_triggers"]) - 3} more)'
                print(
                    f"   - {overlap['skill1']} <-> {overlap['skill2']}: "
                    f"{overlap['overlap_pct']}% overlap; shared: {shared}{more}"
                )

        # Print similarity matrix
        if 'similarity_matrix' in self.results and self.results['similarity_matrix']:
            matrix_data = self.results['similarity_matrix']
            skills = matrix_data['skills']
            matrix = matrix_data['matrix']
            
            print(f"\n📊 Skill Similarity Matrix (Jaccard)")
            
            # Calculate column width based on skill names
            max_name_len = max(len(s) for s in skills)
            col_width = max(6, min(max_name_len, 12))
            
            # Header row with abbreviated skill names
            abbrevs = [s[:col_width] for s in skills]
            header = "   " + " " * (max_name_len + 2) + " | ".join(f"{a:>{col_width}}" for a in abbrevs)
            print(header)
            print("   " + "-" * len(header))
            
            # Data rows
            for i, skill in enumerate(skills):
                row_values = []
                for j, val in enumerate(matrix[i]):
                    if i == j:
                        row_values.append(f"{'---':^{col_width}}")
                    elif val >= 0.3:
                        row_values.append(f"{val:>{col_width}.0%}🚨")
                    elif val >= 0.2:
                        row_values.append(f"{val:>{col_width}.0%}⚠️")
                    else:
                        row_values.append(f"{val:>{col_width}.0%}")
                row_str = " | ".join(row_values)
                print(f"   {skill:<{max_name_len}} | {row_str}")
            
            print(f"\n   Legend: 🚨 >=30% (critical), ⚠️ 20-30% (review), values show Jaccard similarity")
        
        if self.results['broken_references']:
            print(f"\n🔗 Broken references: {len(self.results['broken_references'])}")
            for ref in self.results['broken_references']:
                print(f"   - {ref['skill']}: {ref['path']}")

        if self.results['common_infra_issues']:
            print(f"\n🏗️  Common-infra compliance issues: {len(self.results['common_infra_issues'])}")
            for issue in self.results['common_infra_issues']:
                print(f"   - {issue['skill']}: {issue['message']}")
        
        # Print token costs
        if self.results['token_costs']:
            print(f"\n💰 TOKEN COSTS")
            print(f"   {'Skill':<30} {'Tokens':>12} {'Files':>8}")
            print(f"   {'-'*30} {'-'*12} {'-'*8}")
            
            # Sort by tokens descending
            sorted_costs = sorted(
                self.results['token_costs'].items(),
                key=lambda x: -x[1]['total']
            )
            
            total_tokens = 0
            for skill_name, token_data in sorted_costs:
                tokens = token_data['total']
                files = len(token_data['files'])
                total_tokens += tokens
                
                # Add warning indicator
                indicator = ""
                if tokens > self.TOKEN_THRESHOLD_CRITICAL:
                    indicator = " 🚨"
                elif tokens > self.TOKEN_THRESHOLD_WARNING:
                    indicator = " ⚠️"
                
                print(f"   {skill_name:<30} {tokens:>12,} {files:>8}{indicator}")
            
            print(f"   {'-'*30} {'-'*12} {'-'*8}")
            total_indicator = " ⚠️" if total_tokens > self.TOKEN_THRESHOLD_TOTAL else ""
            print(f"   {'TOTAL':<30} {total_tokens:>12,}{total_indicator}")
            
            # Print detailed breakdown for large skills
            large_skills = [(s, d) for s, d in sorted_costs if d['total'] > self.TOKEN_THRESHOLD_WARNING]
            if large_skills:
                print(f"\n   Detailed breakdown (skills > {self.TOKEN_THRESHOLD_WARNING:,} tokens):")
                for skill_name, token_data in large_skills:
                    print(f"\n   {skill_name} ({token_data['total']:,} tokens):")
                    for f in token_data['files'][:5]:  # Top 5 files
                        pct = (f['tokens'] / token_data['total'] * 100) if token_data['total'] > 0 else 0
                        print(f"      {f['path']:<40} {f['tokens']:>8,} ({pct:>5.1f}%)")
        
        # Generate and print recommendations
        self.generate_recommendations()
        
        if self.results['recommendations']:
            print(f"\n📋 RECOMMENDATIONS ({len(self.results['recommendations'])})")
            
            # Group by severity
            critical_recs = [r for r in self.results['recommendations'] if r['severity'] == 'CRITICAL']
            warning_recs = [r for r in self.results['recommendations'] if r['severity'] == 'WARNING']
            
            if critical_recs:
                print(f"\n   🚨 Critical ({len(critical_recs)}):")
                for rec in critical_recs:
                    skill_str = f"[{rec['skill']}] " if rec['skill'] else ""
                    print(f"      {skill_str}{rec['message']}")
            
            if warning_recs:
                print(f"\n   ⚠️  Warnings ({len(warning_recs)}):")
                for rec in warning_recs:
                    skill_str = f"[{rec['skill']}] " if rec['skill'] else ""
                    print(f"      {skill_str}{rec['message']}")
        
        if self.results['overall_status'] == 'CRITICAL':
            print(f"\n❌ RESULT: FAILED - {self.results['critical_count']} critical issue(s)")
            return False
        elif self.results['overall_status'] == 'WARNING':
            print(f"\n⚠️  RESULT: PASSED with {self.results['warning_count']} warning(s)")
            return True
        else:
            print(f"\n✅ RESULT: PASSED - All quality checks passed!")
            return True
    
    def save_report(self, output_file: str = 'quality-report.json'):
        """Save quality report to JSON file."""
        # Convert sets to lists for JSON serialization
        for skill_name, skill_data in self.all_skills.items():
            if 'triggers' in skill_data and isinstance(skill_data['triggers'], set):
                skill_data['triggers'] = list(skill_data['triggers'])
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Report saved to: {output_file}")


def main():
    """Main entry point for CI/CD pipeline."""
    _configure_windows_unicode_stdout()
    checker = QualityChecker()
    
    try:
        passed = checker.scan_repository()
        checker.save_report()
        
        if checker.results['overall_status'] == 'CRITICAL':
            print("\n❌ CRITICAL ISSUES FOUND - BUILD FAILED")
            sys.exit(1)
        else:
            print("\n✅ QUALITY CHECK COMPLETE")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n💥 QUALITY CHECK FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
