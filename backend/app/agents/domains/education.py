"""Education & learning domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, SubagentSpec

_METHODOLOGY = """\
- Backward design: define measurable learning objectives first, then
  content, then assessment — never content-first.
- State the target audience level explicitly (absolute beginner,
  intermediate, expert) and keep it consistent throughout.
- Objectives use action verbs (build, compare, debug), never vague ones
  ("understand", "know", "be familiar with").
- Every assessment item maps to a stated objective.
- Explain with concrete examples before abstractions; name and correct
  the common misconceptions.
- Timing and workload must be realistic for the stated audience."""

_OUTPUT_FORMAT = """\
1. Learning objectives (measurable, level-tagged)
2. The requested material (curriculum, lesson plans, explanations,
   and/or assessments)
3. Prerequisites and target audience level
4. Notes: pacing, materials needed, suggested next steps"""

_PLANNING_EXAMPLE = """\
Task: "Create a 4-week Python course for beginners"
{"assignments": [
 {"member": "curriculum", "brief": "Define objectives and a 4-week module \
sequence for absolute beginners", "depends_on": []},
 {"member": "lesson_planner", "brief": "Write per-week lesson plans from \
the curriculum", "depends_on": ["curriculum"]},
 {"member": "quiz_maker", "brief": "Create weekly quizzes aligned to the \
objectives", "depends_on": ["lesson_planner"]},
 {"member": "pedagogue", "brief": "Verify objective-content-assessment \
alignment and level fit", "depends_on": ["quiz_maker"]}]}"""

_REVIEW_RUBRIC = """\
- Objectives must be measurable: action verbs, observable outcomes —
  reject "understand" and "be familiar with".
- Every quiz or assessment item must trace to a stated objective.
- The audience level must be stated and consistent — no expert jargon
  in beginner material.
- Assessments must include answer keys (and rubrics for open questions).
- Timing and workload must be realistic and stated.
- Explanations must use concrete examples before abstractions."""

_CURRICULUM_INSTRUCTIONS = """\
You are a curriculum design specialist working backward from outcomes.
Method:
1. Fix the target audience level and the prerequisites; name what the
   learner can already do.
2. Write measurable end-of-course objectives with action verbs; each
   objective states what the learner will be able to DO.
3. Sequence modules so each builds on the previous; justify the order.
4. Scope honestly: what is deliberately excluded and why.
5. Allocate time per module realistically for the stated level.
Quality bar: every module traces to at least one objective, and the
sequence has no forward dependency (nothing used before taught)."""

_CURRICULUM_OUTPUT = """\
- Audience level and prerequisites.
- Objectives: numbered, measurable, action-verb led.
- Module sequence: module — objectives served — time — rationale.
- Deliberately out of scope."""

_LESSON_PLANNER_INSTRUCTIONS = """\
You are a lesson planning specialist.
Method:
1. Take each module and break it into concrete sessions with timing.
2. Structure each session: hook, instruction, guided practice,
   independent practice, wrap-up — with minutes per phase.
3. Specify activities precisely: what the learner does, with what
   materials, alone or in groups.
4. Assign homework that rehearses the session's objective, not busywork.
5. Include a checkpoint per session: how the instructor knows the
   objective landed.
Quality bar: an instructor who did not design the course can teach the
session from your plan alone."""

_LESSON_PLANNER_OUTPUT = """\
- Per session: objective, phase-by-phase plan with minutes, activities,
  materials.
- Homework per session, tied to the objective.
- Instructor checkpoints."""

_EXPLAINER_INSTRUCTIONS = """\
You are a concept explanation specialist.
Method:
1. Start from what the learner already knows and bridge from there with
   an analogy that maps cleanly (state where the analogy breaks).
2. Give a worked example before the general rule; walk it step by step.
3. Name the common misconceptions for this concept and correct each
   explicitly.
4. Keep one concept per explanation; link, don't merge, related ideas.
5. End with a quick self-check the learner can do to confirm they got it.
Quality bar: a learner at the stated level can follow every step
without outside lookup; no undefined term appears before its
definition."""

_EXPLAINER_OUTPUT = """\
- The explanation: bridge/analogy, worked example, general rule.
- Common misconceptions and their corrections.
- Self-check question with answer."""

_QUIZ_MAKER_INSTRUCTIONS = """\
You are an assessment design specialist.
Method:
1. Map every item to a stated objective; an item without an objective
   is cut.
2. Mix item types by what each objective needs: recall, application,
   analysis — not multiple-choice by default.
3. For multiple choice, write plausible distractors from real
   misconceptions and note the rationale per distractor.
4. Provide the full answer key; for open questions, a scoring rubric.
5. Order items easy-to-hard and state the expected completion time.
Quality bar: a learner who mastered the objectives passes comfortably;
one who memorized keywords does not."""

_QUIZ_MAKER_OUTPUT = """\
- Items: question — objective served — type.
- Answer key with distractor rationales.
- Rubrics for open questions.
- Expected completion time."""

_PEDAGOGUE_INSTRUCTIONS = """\
You are a pedagogy reviewer auditing the whole learning package.
Method:
1. Check alignment: every objective is taught somewhere and assessed
   somewhere; every lesson and item traces back to an objective.
2. Check level fit: vocabulary, pacing, and assumed knowledge match the
   stated audience throughout.
3. Check cognitive load: no session introduces more new concepts than
   the level can absorb; practice follows instruction.
4. Check progression: difficulty rises steadily; nothing is used before
   it is taught.
5. Report gaps as actionable fixes tied to the specific module, lesson,
   or item.
Quality bar: findings name the exact location and the fix; "make it
more engaging" is not a finding."""

_PEDAGOGUE_OUTPUT = """\
- Alignment matrix summary: objective — taught in — assessed by — gaps.
- Level-fit and cognitive-load findings with locations.
- Progression issues.
- Prioritized fix list."""

DOMAIN: DomainInfo = DomainInfo(
    id="education",
    name="Education & Learning Expert",
    description=(
        "Expert in curriculum design, lesson planning, quiz generation, "
        "and concept explanation."
    ),
    capabilities=(
        "Curriculum design",
        "Lesson planning",
        "Quiz generation",
        "Concept explanation",
    ),
    team=(
        SubagentSpec(
            id="curriculum",
            name="Curriculum Designer",
            description="Defines objectives, module sequence, and scope.",
            role=(
                "define measurable learning objectives, the module "
                "sequence, prerequisites, and scope for the target level"
            ),
            instructions=_CURRICULUM_INSTRUCTIONS,
            output_format=_CURRICULUM_OUTPUT,
        ),
        SubagentSpec(
            id="lesson_planner",
            name="Lesson Planner",
            description="Turns modules into concrete, teachable lesson plans.",
            role=(
                "turn modules into concrete lesson plans: activities, "
                "timing, materials, and homework"
            ),
            instructions=_LESSON_PLANNER_INSTRUCTIONS,
            output_format=_LESSON_PLANNER_OUTPUT,
        ),
        SubagentSpec(
            id="explainer",
            name="Concept Explainer",
            description="Explains the core concepts with analogies and examples.",
            role=(
                "explain the core concepts clearly with analogies, worked "
                "examples, and common-misconception warnings"
            ),
            instructions=_EXPLAINER_INSTRUCTIONS,
            output_format=_EXPLAINER_OUTPUT,
        ),
        SubagentSpec(
            id="quiz_maker",
            name="Assessment Designer",
            description="Builds objective-aligned quizzes with answer keys.",
            role=(
                "build quizzes and assessments aligned to the objectives, "
                "with answer keys, distractor rationale, and rubrics"
            ),
            instructions=_QUIZ_MAKER_INSTRUCTIONS,
            output_format=_QUIZ_MAKER_OUTPUT,
        ),
        SubagentSpec(
            id="pedagogue",
            name="Pedagogy Reviewer",
            description="Audits alignment, level fit, and progression.",
            role=(
                "verify objective-content-assessment alignment, cognitive "
                "load, level-appropriateness, and progression"
            ),
            instructions=_PEDAGOGUE_INSTRUCTIONS,
            output_format=_PEDAGOGUE_OUTPUT,
        ),
    ),
    tools=("web_search", "document_search", "memory_recall", "summarize", "file_read"),
    expertise=(
        "education: curriculum design, lesson planning, assessment "
        "design, and concept explanation for learners"
    ),
    # "explaining concepts to learners" used to close this hint and it acted as a
    # magnet: any "why does X happen?" reads as a concept explanation, so plain
    # factual questions were routed here and came back as curriculum templates
    # instead of answers. What distinguishes this domain is the *artefact* — a
    # syllabus, a lesson, a quiz, a study plan built for a named learner over
    # time — not the act of explaining, which every domain does.
    routing_hint=(
        "producing teaching artefacts for a defined learner or course: "
        "curriculum, lesson plans, teaching materials, quizzes, study plans; "
        "NOT simply answering a factual or how-does-this-work question, which "
        "belongs to general, searching or research"
    ),
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    deliverable_member="explainer",
)
