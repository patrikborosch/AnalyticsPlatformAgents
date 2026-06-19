#!/usr/bin/env python3
"""
PR-based Changelog Generator for skills-for-fabric
Generates changelog entries from merged PRs since last release.

Usage:
    python generate_changelog.py                    # Preview unreleased changes
    python generate_changelog.py --update           # Update CHANGELOG.md [Unreleased] section
    python generate_changelog.py --release 0.2.0   # Finalize release with version number

Requires: GITHUB_TOKEN environment variable for API access (or uses git log as fallback)
"""
import subprocess
import re
import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

# PR title prefixes/labels mapped to changelog sections
CATEGORY_MAP = {
    # Prefixes in PR titles
    'feat': 'Added',
    'feature': 'Added',
    'add': 'Added',
    'new': 'Added',
    'fix': 'Fixed',
    'bug': 'Fixed',
    'hotfix': 'Fixed',
    'docs': 'Documentation',
    'doc': 'Documentation',
    'refactor': 'Changed',
    'update': 'Changed',
    'improve': 'Changed',
    'enhancement': 'Changed',
    'perf': 'Changed',
    'remove': 'Removed',
    'deprecate': 'Removed',
    'breaking': 'Breaking Changes',
    'security': 'Security',
}

def get_repo_info() -> tuple:
    """Extract owner/repo from git remote."""
    result = subprocess.run(
        ['git', 'remote', 'get-url', 'origin'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None, None
    
    url = result.stdout.strip()
    # Parse: https://github.com/owner/repo.git or git@github.com:owner/repo.git
    match = re.search(r'github\.com[/:]([^/]+)/([^/.]+)', url)
    if match:
        return match.group(1), match.group(2).replace('.git', '')
    return None, None

def get_last_version_tag() -> Optional[str]:
    """Get the most recent version tag."""
    result = subprocess.run(
        ['git', 'describe', '--tags', '--abbrev=0', '--match', 'v*'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None

def get_merged_prs_from_github(owner: str, repo: str, since_tag: str = None) -> List[Dict]:
    """Fetch merged PRs from GitHub API."""
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("⚠️  GITHUB_TOKEN not set, falling back to git log")
        return None
    
    # Get tag date if provided
    since_date = None
    if since_tag:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%aI', since_tag],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            since_date = result.stdout.strip()
    
    # Fetch merged PRs
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100"
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'skills-for-fabric-Changelog'
    }
    
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as response:
            prs = json.loads(response.read().decode())
    except URLError as e:
        print(f"⚠️  GitHub API error: {e}")
        return None
    
    merged_prs = []
    for pr in prs:
        if not pr.get('merged_at'):
            continue
        
        # Skip PRs merged before the tag
        if since_date and pr['merged_at'] < since_date:
            continue
        
        labels = [l['name'] for l in pr.get('labels', [])]
        merged_prs.append({
            'number': pr['number'],
            'title': pr['title'],
            'author': pr['user']['login'],
            'merged_at': pr['merged_at'][:10],
            'labels': labels,
            'url': pr['html_url']
        })
    
    return merged_prs

def get_merge_commits_from_git(since_tag: str = None) -> List[Dict]:
    """Fallback: get merge commits from git log with better parsing."""
    if since_tag:
        cmd = ['git', 'log', f'{since_tag}..HEAD', '--merges', '--pretty=format:%H|%s|%an|%ad|%b', '--date=short']
    else:
        cmd = ['git', 'log', '--merges', '-20', '--pretty=format:%H|%s|%an|%ad|%b', '--date=short']
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 4:
            # Extract PR number from merge commit message
            pr_match = re.search(r'#(\d+)', parts[1])
            pr_number = int(pr_match.group(1)) if pr_match else None
            
            # Try to get a clean title from merge commit
            title = parts[1]
            body = parts[4] if len(parts) > 4 else ''
            
            # Extract meaningful title from branch name if merge commit
            branch_match = re.search(r'from \S+/(\S+)', title)
            if branch_match:
                branch_name = branch_match.group(1)
                # Convert branch name to readable title
                # feature/spark-sql-odbc -> Spark SQL ODBC
                title = branch_name.replace('feature/', '').replace('fix/', '').replace('/', ' ')
                title = title.replace('-', ' ').replace('_', ' ')
                title = ' '.join(word.capitalize() for word in title.split())
            
            # If there's a body, use first line as title
            if body and body.strip():
                first_line = body.strip().split('\n')[0]
                if len(first_line) > 10 and not first_line.startswith('*'):
                    title = first_line
            
            if title or pr_number:
                commits.append({
                    'number': pr_number,
                    'title': title,
                    'author': parts[2],
                    'merged_at': parts[3],
                    'labels': [],
                    'url': None
                })
    
    return commits

def get_direct_commits_from_git(since_tag: str = None) -> List[Dict]:
    """Get non-merge commits (direct pushes to main)."""
    if since_tag:
        cmd = ['git', 'log', f'{since_tag}..HEAD', '--no-merges', '--pretty=format:%H|%s|%an|%ad', '--date=short']
    else:
        cmd = ['git', 'log', '--no-merges', '-30', '--pretty=format:%H|%s|%an|%ad', '--date=short']
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 3)
        if len(parts) >= 4:
            title = parts[1].strip()
            
            # Skip version bumps, merge commits, etc.
            skip_patterns = ['bump version', 'release v', 'merge', 'update changelog']
            if any(p in title.lower() for p in skip_patterns):
                continue
            
            commits.append({
                'number': None,
                'title': title,
                'author': parts[2],
                'merged_at': parts[3],
                'labels': [],
                'url': None,
                'hash': parts[0][:7]
            })
    
    return commits

def categorize_pr(pr: Dict) -> str:
    """Determine changelog category from PR title or labels."""
    title_lower = pr['title'].lower()
    
    # Check labels first
    for label in pr.get('labels', []):
        label_lower = label.lower()
        for prefix, category in CATEGORY_MAP.items():
            if prefix in label_lower:
                return category
    
    # Check title prefix
    for prefix, category in CATEGORY_MAP.items():
        if title_lower.startswith(prefix) or title_lower.startswith(f'[{prefix}]'):
            return category
    
    # Default
    return 'Changed'

def format_pr_entry(pr: Dict, include_pr_link: bool = True) -> str:
    """Format a PR as a changelog entry."""
    title = pr['title']
    
    # Remove common prefixes from title
    title = re.sub(r'^\[(feat|fix|docs|chore|refactor|add|update)\]\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^(feat|fix|docs|chore|refactor|add|update)[\s:]+', '', title, flags=re.IGNORECASE)
    
    # Capitalize first letter
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    
    # Add PR link if available
    if include_pr_link and pr.get('number'):
        if pr.get('url'):
            return f"{title} ([#{pr['number']}]({pr['url']}))"
        else:
            return f"{title} (#{pr['number']})"
    return title

def generate_changelog(prs: List[Dict], version: str = None) -> str:
    """Generate changelog markdown from PRs."""
    # Categorize PRs
    sections: Dict[str, List[str]] = {}
    
    for pr in prs:
        category = categorize_pr(pr)
        if category not in sections:
            sections[category] = []
        entry = format_pr_entry(pr)
        if entry not in sections[category]:
            sections[category].append(entry)
    
    # Generate markdown
    lines = []
    if version:
        date = datetime.now().strftime('%Y-%m-%d')
        lines.append(f"## [{version}] - {date}")
    else:
        lines.append("## [Unreleased]")
    lines.append("")
    
    # Order: Breaking Changes, Added, Changed, Fixed, Removed, Security, Documentation
    section_order = ['Breaking Changes', 'Added', 'Changed', 'Fixed', 'Removed', 'Security', 'Documentation']
    
    for section_name in section_order:
        if section_name in sections and sections[section_name]:
            lines.append(f"### {section_name}")
            for entry in sections[section_name]:
                lines.append(f"- {entry}")
            lines.append("")
    
    return '\n'.join(lines)

def update_changelog_file(new_content: str, version: str = None):
    """Update CHANGELOG.md with new content."""
    changelog_path = Path('CHANGELOG.md')
    
    if not changelog_path.exists():
        print("❌ CHANGELOG.md not found")
        return False
    
    content = changelog_path.read_text(encoding='utf-8')
    
    if version:
        # For release: replace [Unreleased] content and add version section
        # Find [Unreleased] section
        unreleased_match = re.search(r'(## \[Unreleased\])\s*\n', content)
        if not unreleased_match:
            print("❌ Could not find [Unreleased] section")
            return False
        
        # Find next version section
        next_version = re.search(r'\n(## \[\d+\.\d+\.\d+\])', content[unreleased_match.end():])
        
        if next_version:
            end_pos = unreleased_match.end() + next_version.start()
        else:
            end_pos = len(content)
        
        # Build new content: keep [Unreleased] header empty, add version section
        new_changelog = (
            content[:unreleased_match.end()] + 
            '\n' +
            new_content + 
            '\n' +
            content[end_pos:]
        )
    else:
        # For preview: just show what would be added under [Unreleased]
        unreleased_match = re.search(r'(## \[Unreleased\])\s*\n', content)
        if not unreleased_match:
            print("❌ Could not find [Unreleased] section")
            return False
        
        next_version = re.search(r'\n(## \[\d+\.\d+\.\d+\])', content[unreleased_match.end():])
        
        if next_version:
            end_pos = unreleased_match.end() + next_version.start()
        else:
            end_pos = len(content)
        
        # Replace [Unreleased] content
        new_changelog = (
            content[:unreleased_match.end()] + 
            '\n' +
            new_content.replace('## [Unreleased]\n\n', '') +  # Remove duplicate header
            content[end_pos:]
        )
    
    changelog_path.write_text(new_changelog, encoding='utf-8')
    print(f"✅ Updated CHANGELOG.md")
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate changelog from merged PRs')
    parser.add_argument('--update', action='store_true', help='Update CHANGELOG.md')
    parser.add_argument('--release', type=str, metavar='VERSION', help='Finalize release with version (e.g., 0.2.0)')
    parser.add_argument('--include-commits', action='store_true', help='Include direct commits (not just PRs)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("📋 CHANGELOG GENERATOR")
    print("=" * 60)
    
    # Get repo info
    owner, repo = get_repo_info()
    if owner and repo:
        print(f"📦 Repository: {owner}/{repo}")
    
    # Get last tag
    last_tag = get_last_version_tag()
    if last_tag:
        print(f"📌 Last release: {last_tag}")
    else:
        print("📌 No version tags found (showing recent changes)")
    
    print()
    
    # Get PRs
    prs = None
    if owner and repo:
        prs = get_merged_prs_from_github(owner, repo, last_tag)
    
    if prs is None:
        print("📋 Fetching from git history...")
        prs = get_merge_commits_from_git(last_tag)
    
    # Optionally add direct commits
    if args.include_commits:
        direct_commits = get_direct_commits_from_git(last_tag)
        if direct_commits:
            print(f"   + {len(direct_commits)} direct commit(s)")
            prs = prs + direct_commits
    
    if not prs:
        print("\n✅ No changes since last release")
        return
    
    print(f"\n📝 Changes since last release: {len(prs)} item(s)\n")
    
    # Show what we found
    print("─" * 60)
    print("ITEMS FOUND:")
    print("─" * 60)
    for i, pr in enumerate(prs, 1):
        category = categorize_pr(pr)
        pr_ref = f"#{pr['number']}" if pr.get('number') else pr.get('hash', '')[:7]
        print(f"  {i}. [{category}] {pr['title'][:50]}{'...' if len(pr['title']) > 50 else ''} ({pr_ref})")
    print()
    
    # Generate changelog
    version = args.release if args.release else None
    changelog = generate_changelog(prs, version)
    
    print("─" * 60)
    print("GENERATED CHANGELOG:")
    print("─" * 60)
    print(changelog)
    print("─" * 60)
    print("─" * 60)
    
    if args.update or args.release:
        update_changelog_file(changelog, version)
        if args.release:
            print(f"\n🎉 Ready to release v{args.release}")
            print(f"   Next steps:")
            print(f"   1. Review CHANGELOG.md")
            print(f"   2. git add CHANGELOG.md && git commit -m 'Release v{args.release}'")
            print(f"   3. git tag v{args.release}")
            print(f"   4. git push && git push --tags")
    else:
        print("\n💡 Options:")
        print("   --update        Update [Unreleased] section in CHANGELOG.md")
        print("   --release X.Y.Z Finalize release with version number")

if __name__ == "__main__":
    main()
