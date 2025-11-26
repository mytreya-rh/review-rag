Perform a critical architectural review of the provided PR against @guidelines_clustered.json. 

## ANALYSIS APPROACH
- **Be skeptical**: Question necessity and design choices
- **Security-first**: Identify bypass scenarios and validation gaps  
- **First principles**: Don't accept PR justifications uncritically
- **Apply guidelines actively**: Reference specific lines/clusters

## FOR EACH NEW FEATURE/API FIELD

### 1. Necessity Analysis
- Is this required for documented use cases, or premature generalization?
- Can users already accomplish this through standard Kubernetes patterns?
- Does operator involvement add value, or just complexity?
- Check: **extensibility guidelines**

### 2. Security Analysis (Critical for Security Features)
- **Worst-case misuse scenario**: What if user provides malicious input?
- **Bypass potential**: Can this feature undermine its own security model?
- **Validation gaps**: What prevents allow-all, overly broad, or empty rules?
- Check: **config-safety**
- Check: **validation-strictness**

### 3. Alternative Designs
- What simpler alternatives exist?
- Could this be more constrained (specific patterns vs arbitrary input)?
- Can responsibility stay with users instead of operator?
- What's the maintenance burden vs benefit tradeoff?

### 4. Validation & Correctness
- Are CEL validations preventing invalid/insecure configurations?
- Does implementation match documentation exactly?
- Are immutability constraints enforced?
- Check: **correctness**

### 5. Resource Management
- Are owner references set for garbage collection?
- Are controller watches established for drift detection?
- Check: **resource-lifecycle**

## EXPLICIT GUIDELINE CHECKS

Apply these guidelines to every PR:

### Security & Validation
- [ ] **config-safety** 
- [ ] **validation-strictness** 
- [ ] **feature-immutability** 
- [ ] **correctness** 

### API Design
- [ ] **extensibility** 
- [ ] **api-compatibility** 
- [ ] **ease-of-use** 

### Operations & Lifecycle  
- [ ] **resource-lifecycle** 
- [ ] **upgrade-safety** 
- [ ] **maintainability** 


## OUTPUT FORMAT

Structure the review as:

### 🚨 ARCHITECTURAL FLAWS (if any)
Fundamental design issues requiring removal or significant redesign:
- What: Describe the flaw
- Why problematic: Cite specific guidelines violated
- Recommendation: Remove, redesign, or constrain

### 🔴 CRITICAL Issues (Must Fix Before Release)
Issues that risk correctness, security, or upgrade safety:
- What, Why, How to fix, Guideline reference

### 🟡 MEDIUM Priority (Should Address)
Important issues that reduce quality but not blocking:
- What, Why, Recommendation, Guideline reference

### ✅ STRENGTHS
Positive patterns that align with guidelines:
- What pattern, Which guideline, Why it's good

### ⚠️ NEEDS VERIFICATION
Areas requiring deeper investigation or code review:
- What to verify, Why it matters, How to check

### 💡 FUTURE CONSIDERATIONS
Non-blocking observations for future iterations

## FOR SECURITY-RELATED FEATURES

Explicitly answer these questions:

1. **Can users bypass this security control?**
   - What validation prevents this?

2. **What's the attack surface?**
   - What inputs are user-controlled?
   - What's the worst thing a malicious user could do?

3. **Are constraints sufficient?**
   - CEL validations in place?
   - Admission-time vs runtime validation?
   - Immutability enforced where needed?

4. **Does this blur security boundaries?**
   - Clear responsibility between operator and user?
   - Who troubleshoots when custom config breaks things?

## FOR NEW API FIELDS

Before accepting new API surface, challenge:

1. **Is operator involvement necessary?**
   - "Why can't users do this with standard K8s resources?"
   
2. **Is this premature generalization?**
   - "What's the documented requirement driving this?"
   - "Can we start more constrained and expand later if needed?"

3. **What's the maintenance cost?**
   - Validation logic, testing, documentation, support
   - Breaking change risk when tightening constraints later

4. **What simpler alternative exists?**
   - Direct K8s resources instead of operator API?
   - Constrained patterns instead of arbitrary input?
   - Hard-coded reasonable defaults instead of configuration?

## REMEMBER

- **Don't accept PR descriptions uncritically** - they may justify features without considering downsides
- **Security bypasses are architectural flaws** - not just implementation bugs
- **Unnecessary API surface is technical debt** - harder to remove than to not add
- **Question every new field** - "Is this actually required, or nice-to-have complexity?"
- **Cite specific guidelines** - reference cluster IDs and line numbers from JSON

## EXAMPLE CRITICAL ANALYSIS

Good example of skeptical analysis:

```
🚨 ARCHITECTURAL FLAW: Custom Authentication Provider Configuration

**What**: PR adds `authProviders` field allowing users to define custom OIDC/LDAP configs

**Challenge Necessity**:
- Why can't users configure authentication via standard K8s Secrets and ConfigMaps?
- Is operator involvement required, or just wrapping existing K8s patterns?
- Violates: extensibility (Cluster 4, lines 551-560) - unnecessary API surface

**Security Risk Analysis**:
- User could specify `allowInsecure: true` → bypass TLS verification
- No validation preventing weak auth methods (e.g., basic auth without TLS)
- Credential handling in CRD creates audit trail gaps
- Violates: config-safety (Cluster 1, lines 857-865) - overly permissive configuration

**Validation Gaps**:
- No CEL validation preventing empty clientSecret
- No check that issuerURL uses https://
- Missing validation for redirect URL patterns
- Violates: validation-strictness (Cluster 1, lines 834-843)

**Alternative Design**:
- Operator supports ONLY pre-approved, hardened auth configurations
- Users reference existing K8s Secret with OIDC credentials
- Operator validates Secret format, doesn't accept inline config

**Recommendation**: 
1. REMOVE arbitrary auth provider configuration
2. REPLACE with constrained pattern:
   ```yaml
   spec:
     authenticationRef:
       kind: Secret
       name: oidc-config
       # Operator validates Secret schema, doesn't expose all fields in CRD
   ```
3. Reduces attack surface, prevents misconfiguration, clarifies responsibility

**Maintenance Impact**:
- Current design requires operator to support all auth provider variations
- Maintenance burden: testing matrix, security patches, compatibility
- Constrained design: operator validates known-good patterns, users manage credentials
```
