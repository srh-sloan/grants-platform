---
name: ux-journey
description: Diagnose and improve end-to-end user experience by mapping journeys, identifying friction, and proposing high-impact, accessible refinements. Use this skill when the user asks for UX critique, flow improvements, onboarding fixes, or product journey optimisation.
---

This skill guides UX diagnosis and improvement of existing products (apps, web pages, dashboards, and even repositories as products). It focuses on how people actually move from intent to outcome, where they get confused or stuck, and what changes will make the experience more functional, accessible, and satisfying.

The user provides a product, flow, repo, or interface to review. They may include goals, constraints, audience, or pain points. Your job is to map the real journey, spot friction with precision, and propose concrete improvements that are implementable.

## UX Thinking

Before proposing solutions, understand the product as a sequence of human decisions under constraints.

- **Purpose**: What job is this product helping the user do? What is the "done" state?
- **Users**: Who uses it, what do they already know, and what are they trying to accomplish right now?
- **Context**: Device, environment, time pressure, accessibility needs, emotional state (stress, urgency, embarrassment, fatigue).
- **Constraints**: Platform conventions, brand constraints, technical limitations, legal or compliance requirements, content dependencies.
- **Success**: Define what "better" means — task success, fewer errors, faster completion, higher conversion, fewer support tickets.

**CRITICAL**: Choose one primary journey and optimise it end-to-end before touching secondary flows. One smooth path beats ten half-finished ones.

Then produce a UX improvement plan that is:
- Specific and actionable (not generic advice)
- Grounded in the current flow (not a hypothetical redesign)
- Accessible by default (keyboard, screen reader, contrast, target sizes, error recovery)
- Consistent with platform conventions and user expectations
- Prioritised by impact and effort

## UX Diagnosis Workflow

Use a repeatable, evidence-seeking approach:

1. **Identify the top tasks**
   - What are the 1 to 3 most common or most valuable things users come here to do?
   - For a repo: install, run, configure, deploy, contribute.

2. **Walk the journey like a real user**
   - Start at entry (landing page, deep link, README, invite email).
   - Track every step until success or abandonment.

3. **Map friction precisely**
   - Ambiguity: "What do I do next?"
   - Cognitive load: too many choices or too much reading
   - Visibility: missing status, hidden system state, unclear progress
   - Error handling: blamey errors, dead ends, unclear recovery
   - Trust: unclear permissions, unclear pricing, scary warnings, missing legitimacy signals
   - Accessibility: keyboard traps, missing focus states, tiny targets, weak contrast, motion issues

4. **Propose fixes at the right altitude**
   - Small, surgical changes first (labels, hierarchy, defaults, layout, feedback, copy, validation).
   - Only suggest structural changes (IA, navigation, flow redesign) when friction is systemic.

5. **Prioritise**
   - Highest leverage changes first (big impact, low effort).
   - Separate "must fix" blockers from "nice to have" polish.

6. **Define how to validate**
   - What metric, test, or observation would confirm the improvement worked?

## Core UX Principles

Apply these as decision tools, not as a checklist.

- **Usability**: Improve effectiveness (can they do it), efficiency (how fast and how painful), and satisfaction (how it feels), always in the context of use.
- **Learnability**: A new user should succeed on the first attempt with minimal explanation.
- **Hierarchy**: Use layout, spacing, type scale, and grouping to make the next action obvious.
- **Consistency**: Patterns should behave the same across the product so users can predict outcomes.
- **Feedback**: Every action should produce a visible, interpretable reaction (loading, success, error, progress).
- **Error prevention and recovery**: Prevent avoidable errors, and make recovery obvious when they happen.
- **Accessibility-first**: Keyboard navigation, focus visibility, readable text, predictable interactions, generous target sizes.

## Psychology and UX Laws

Use these laws as lenses to explain why something feels hard, then tailor the fix to the product.

- **Jakob's Law**: Users expect your product to work like the other products they already know. Use conventions unless you have a strong reason not to.
- **Hick's Law**: More choices means slower decisions. Reduce, group, or sequence choices.
- **Fitts's Law**: Important targets should be easy to hit. Make primary actions larger and closer to the user's focus.
- **Aesthetic-Usability Effect**: Visual polish increases tolerance, but can also mask usability issues. Do not let aesthetics hide broken flows.

**CRITICAL**: Do not name-drop laws to sound smart. Use them only when they clearly explain a specific problem and support a specific fix.

## Accessibility and Inclusive UX Baseline

Treat accessibility as core UX quality, not an optional add-on.

- Ensure full keyboard operability and visible focus states.
- Avoid relying on colour alone for meaning.
- Provide clear labels, error messages, and instructions.
- Make touch targets comfortably sized and spaced.
- Respect reduced-motion preferences and avoid disorienting animation.

## Research, When It Actually Helps

Prefer product-specific evidence first: analytics, logs, support tickets, reviews, user quotes, recordings, and observed behaviour.

Use web research selectively, only when it will change decisions:
- The domain has strong conventions (payments, health, government services, security-sensitive flows).
- You need up-to-date constraints or standards (accessibility guidance, platform rules).
- You need competitor patterns to understand user expectations.

When researching:
- Make queries narrow and domain-specific, not generic ("best onboarding UX" is useless).
- Compare at least two credible sources or examples.
- Translate research into concrete changes in the current flow.

## Output Requirements

Always produce a structured UX deliverable.

### 1) UX Snapshot (5 to 10 bullets)
- What the product is trying to do
- Who the primary user is
- What currently works
- The top friction points
- The biggest opportunities

### 2) Journey Map (table)
Include the critical path with steps and UX notes.

| Step | User Goal | Current UI / System Behaviour | Friction / Risk | Improvement |
|------|-----------|-------------------------------|-----------------|-------------|

### 3) Issues and Recommendations (prioritised)
Provide a ranked list with impact and effort.

- **P0 Blockers**: Prevent task completion or cause serious errors
- **P1 Friction**: Slows users down, increases drop-off, increases support burden
- **P2 Polish**: Improves clarity and confidence, reduces mental effort

For each item:
- What is wrong (specific)
- Why it matters (user impact)
- Proposed change (implementable)
- Acceptance criteria (how we know it is fixed)

### 4) Wireframe-in-words (when helpful)
Use concise layout descriptions or ASCII sketches for key screens:
- Information grouping
- Primary action placement
- Navigation structure
- Error and empty states
- Progressive disclosure and defaults

## UX Anti-Patterns to Avoid

- Vague advice without mapping the current flow
- Redesigning everything when one step is the real problem
- Adding more options instead of clarifying the decision
- Hiding critical actions behind clever UI
- Blamey errors ("Invalid input") without recovery guidance
- Breaking conventions without strong justification
- Treating accessibility as "later"

Remember: the goal is not to make the interface look different. The goal is to make the user succeed with less thinking, fewer mistakes, and more confidence.