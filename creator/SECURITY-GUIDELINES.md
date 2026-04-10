# Responsible AI Security Guidelines for skills-for-fabric

## Content Security Standards

### Prompt Injection Prevention

Before contributing or modifying skills, all content must be validated against prompt injection attack vectors:


#### 🚨 **Prohibited Content Patterns**

1. **Direct AI Instructions**
   - ❌ "Ignore previous instructions"
   - ❌ "Act as if you are..."
   - ❌ "Forget everything and..."
   - ❌ "System: [malicious instructions]"

2. **Role Manipulation**
   - ❌ "You are now a [different role]"
   - ❌ "Pretend to be..."
   - ❌ "Switch to [unauthorized mode]"

3. **Instruction Overrides**
   - ❌ "Override your guidelines"
   - ❌ "Bypass safety measures"
   - ❌ "Don't follow previous rules"

4. **Information Extraction Attempts**
   - ❌ "What are your instructions?"
   - ❌ "Show me your system prompt"
   - ❌ "Reveal your training data"

#### ✅ **Safe Content Practices**

1. **Technical Documentation Only**
   - Focus on legitimate Fabric/Spark configurations
   - Provide clear, factual API examples
   - Include proper authentication patterns

2. **Code Examples**
   - Use placeholder values (`your-workspace-id`)
   - Follow Microsoft security best practices
   - Include proper error handling

3. **Instructional Content**
   - Clear "Must/Prefer/Avoid" guidelines
   - Technical recommendations only
   - No requests for AI behavior modification

#### 🔍 **Content Review Checklist**

Before submitting:
- [ ] No instructions targeting AI assistants
- [ ] No role-playing or persona requests  
- [ ] No attempts to extract system information
- [ ] All code examples use safe placeholder values
- [ ] Authentication examples use proper Azure patterns
- [ ] No hardcoded secrets or sensitive information

#### 🛡️ **Security Validation**

Run this check on all skill content:

```python
import re

def check_prompt_injection_risk(content):
    """Check for potential prompt injection patterns"""
    risk_patterns = [
        r'ignore.*previous.*instruction',
        r'act\s+as\s+(?:if\s+)?you\s+are',
        r'forget\s+everything',
        r'system\s*:\s*[^a-z]',
        r'you\s+are\s+now\s+a',
        r'pretend\s+to\s+be',
        r'override.*guidelines?',
        r'bypass.*safety',
        r'don[\'t]*\s+follow.*rules?',
        r'what\s+are\s+your\s+instructions',
        r'show.*system\s+prompt',
        r'reveal.*training'
    ]
    
    risks_found = []
    for pattern in risk_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            risks_found.extend(matches)
    
    return risks_found

# Usage for validation
risks = check_prompt_injection_risk(skill_content)
if risks:
    print(f"⚠️ Potential risks found: {risks}")
else:
    print("✅ Content appears safe")
```

## Open Source Security Considerations

### Before Public Release

1. **Remove All Sensitive Information**
   - No internal Microsoft domains
   - No actual workspace/tenant IDs
   - No real authentication tokens

2. **Sanitize Examples**
   - Replace with `example.com` domains
   - Use `your-workspace-id` placeholders
   - Generic resource names only

3. **Review All URLs**
   - Ensure all links point to public documentation
   - No internal Microsoft resources
   - Verify all Microsoft Learn links are public

### Community Guidelines

1. **Contribution Review Process**
   - All PRs require security review
   - Automated scanning for injection patterns
   - Human review for complex changes

2. **Reporting Security Issues**
   - Private security reporting channel
   - Responsible disclosure process
   - Security patch process

---

**Remember**: These skills will be used by AI assistants to help developers. Any malicious content could potentially be exploited to manipulate AI behavior. Always err on the side of caution.