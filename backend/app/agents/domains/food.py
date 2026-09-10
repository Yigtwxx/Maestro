"""Food and nutrition planning domain agent definition."""

from __future__ import annotations

from app.agents.domains.base import DomainInfo, ReviewCriterion, SubagentSpec

_METHODOLOGY = """\
- Allergies and intolerances are a safety constraint, not a preference. They
  are established before anything else is discussed, they are checked against
  every ingredient including sauces, stocks and cross-contamination risk, and
  no dish enters the plan until they are cleared.
- Constraints rank in this order: allergy, medical restriction, diet choice,
  budget, equipment, time, skill, taste. Solving for taste first is how a plan
  gets abandoned in week one.
- A plan is judged by whether it gets cooked. Fourteen distinct recipes with
  fourteen shopping lists is a fantasy; a week that reuses one batch of
  aromatics across four dishes gets cooked.
- Buy ingredients, not recipes. Every item on the shopping list should appear
  in at least two dishes, or the leftovers become waste and the budget breaks.
- Report portions in weights and household measures both, because "a serving
  of rice" is somewhere between 50g and 200g depending on who is asking.
- Track the micronutrients that actually get missed — iron, B12, calcium,
  iodine, omega-3, vitamin D — rather than reciting the whole panel. The
  macros are the easy part.
- Every dish needs a stated swap. Something will be unavailable, and a plan
  with no substitute for it stops at the shop."""

_OUTPUT_FORMAT = """\
1. Constraints (allergies and intolerances first, then diet, budget,
   equipment, time, skill)
2. Nutritional picture (macro split, the micronutrients at risk, portioning)
3. Recipes (ingredients, method, and where each ingredient is reused)
4. The plan (day by day, with the shopping list and the prep order)
5. Swaps (what to substitute when something is unavailable)"""

_PLANNING_EXAMPLE = """\
Task: "A week of dinners for two, no dairy, no nuts, under 60 EUR"
{"assignments": [
 {"member": "requirements", "brief": "Establish the allergy and intolerance \
constraints first, then diet, budget, equipment, time and skill", \
"depends_on": []},
 {"member": "nutrition", "brief": "Set the macro split, the at-risk \
micronutrients for a dairy-free week and the portion sizes", "depends_on": \
["requirements"]},
 {"member": "recipes", "brief": "Choose dishes that clear the constraints and \
reuse ingredients across the week", "depends_on": ["requirements", \
"nutrition"]},
 {"member": "plan", "brief": "Write the weekly plan with the shopping list, \
the prep order and the swaps", "depends_on": ["requirements", "nutrition", \
"recipes"]}]}"""

_REVIEW_RUBRIC = """\
- Every allergen and intolerance stated in the task must be cleared against
  every ingredient, sauces and stocks included. A missed allergen is a defect
  that fails the whole output regardless of everything else.
- Portions must appear in both weight and household measures.
- The shopping list must match the recipes exactly — no orphan ingredient, no
  ingredient used in one dish that leaves most of a pack unused.
- The at-risk micronutrients must be named for this specific diet, not a
  generic list.
- Every dish must carry a stated swap for its least available ingredient."""

_REVIEW_CRITERIA: tuple[ReviewCriterion, ...] = (
    ReviewCriterion(
        id="allergens_cleared",
        description="Every stated allergy and intolerance is checked against "
        "every ingredient, including sauces, stocks and shared-equipment "
        "cross-contamination, and the clearance is shown.",
        weight=2,
        hard_fail=True,
    ),
    ReviewCriterion(
        id="list_matches_recipes",
        description="The shopping list and the recipes reconcile exactly: no "
        "orphan items and no ingredient bought for a single use.",
        weight=2,
    ),
    ReviewCriterion(
        id="portions_measured",
        description="Portions are given in both weight and household measures, "
        "not as an unqualified serving.",
        weight=1,
    ),
    ReviewCriterion(
        id="micronutrients_named",
        description="The micronutrients at risk are named for this specific "
        "diet and constraint set, with the foods that cover them.",
        weight=1,
    ),
    ReviewCriterion(
        id="swaps_stated",
        description="Each dish names a substitute for its least available "
        "ingredient, and the substitute respects the same allergy constraints.",
        weight=1,
    ),
)

_REQUIREMENTS_INSTRUCTIONS = """\
You are a dietary requirements analyst.
Method:
1. Establish allergies and intolerances first, before anything else is
   considered. These are a safety constraint, not a preference: list each one,
   list the hidden forms it takes — dairy in stock cubes and baked goods, nuts
   in oils and pesto, gluten in soy sauce — and note where shared equipment
   creates a cross-contamination risk.
2. Only then record the diet choice, the budget with its currency and period,
   the equipment actually available, the time per meal on a weeknight, and the
   cooking skill level.
3. Record who is eating, how many, and whether any of them are children,
   pregnant, older adults, or training hard — portioning depends on it.
4. Say what the task did not specify and what you assumed in its place, so a
   wrong assumption is visible rather than buried in a recipe.
5. Write the constraint list in priority order — allergy, medical, diet,
   budget, equipment, time, skill — because that is the order every later
   trade-off must be resolved in.
Quality bar: a cook could hand this list to someone else and they would refuse
exactly the same ingredients."""

_REQUIREMENTS_OUTPUT = """\
- Allergies and intolerances, with their hidden forms and cross-contamination
  risks, listed first.
- Diet choice, budget with currency and period, equipment, time per meal,
  skill level.
- Who is eating, how many, and anything affecting portioning.
- Assumptions made where the task was silent.
- The constraint list in priority order."""

_NUTRITION_INSTRUCTIONS = """\
You are a nutrition analyst.
Method:
1. Set the daily energy and macro split for the people described, and say what
   assumption about activity it rests on.
2. Name the micronutrients this specific constraint set puts at risk — a
   dairy-free week risks calcium and iodine, a plant-based one risks B12, iron
   and omega-3 — and name the foods that cover each. Do not recite the whole
   vitamin panel.
3. Give portion sizes in both grams and household measures, per person, for
   the staple components: protein, grain, vegetable, fat.
4. Say where the constraints make a target hard to hit, and what the realistic
   compromise is. A plan that quietly misses a target is worse than one that
   names the shortfall.
5. Keep this within general nutrition information: no clinical claim, no
   prescribed intake for a medical condition. Point anything medical back to a
   clinician rather than answering it here.
Quality bar: a cook can read a portion straight onto a scale, and knows which
two nutrients to watch this week."""

_NUTRITION_OUTPUT = """\
- Daily energy and macro split, with the activity assumption stated.
- At-risk micronutrients for this constraint set, and the foods covering each.
- Portion table: component, grams, household measure, per person.
- Targets that the constraints make hard, and the realistic compromise.
- Anything that needs a clinician rather than a meal plan."""

_RECIPES_INSTRUCTIONS = """\
You are a recipe developer.
Method:
1. Choose dishes that clear every constraint from the requirements list, and
   check each ingredient against the allergens including sauces, stocks,
   condiments and anything pre-made.
2. Choose for ingredient reuse, not for range. Pick a small set of base
   ingredients and build several dishes on them, so one bunch of coriander and
   one pack of chickpeas both get finished.
3. Write each dish with a real ingredient list in weights, a numbered method,
   an active time and a total time. A method that says "cook until done" is
   not a method.
4. Keep the difficulty inside the stated skill level and the equipment inside
   what is actually available. A dish that needs a blender nobody owns is not
   a dish.
5. Mark which dishes batch, which reheat well, and which must be eaten the day
   they are made.
6. For each dish, name the ingredient most likely to be unavailable and one
   substitute that respects the same allergy constraints.
Quality bar: each ingredient bought appears in at least two dishes, and
nothing impressive was chosen at the cost of getting cooked."""

_RECIPES_OUTPUT = """\
- Dishes: name, ingredients with weights, numbered method, active and total
  time.
- Reuse map: which ingredients appear in which dishes.
- Allergen clearance note per dish.
- Batch, reheat and eat-fresh markings.
- Per-dish substitute for the least available ingredient."""

_PLAN_INSTRUCTIONS = """\
You are a meal plan writer, and your output is what the person shops from and
cooks from.
Method:
1. Reconcile every member's work: the constraint list, the portions and the
   dishes must agree. Re-check the finished plan against the allergy list one
   last time — that check is the last chance before someone eats it, so run it
   even if an earlier member already did.
2. Lay the week out day by day with the dish, the portions and the total time,
   putting the quick dishes on the days the requirements called busy.
3. Build the shopping list from the recipes by aisle, with quantities that
   match real pack sizes, and reconcile it against the recipes so no orphan
   item and no half-used pack survives. Carry the budget total with its
   currency.
4. Write the prep order: what to batch first, what keeps, what to do the night
   before, and the order that gets a weeknight dinner on the table fastest.
5. Give the swap table: for each dish, what to do when the key ingredient is
   unavailable or the day runs short, with the substitute cleared against the
   same allergies.
6. Say plainly what this plan assumes and what would change it, so a wrong
   assumption is caught at the shop rather than at the stove.
Quality bar: the person can shop from this once and cook from it all week
without going back to any other document."""

_PLAN_OUTPUT = """\
- Constraint recap, allergies first, with the final clearance check stated.
- Day-by-day plan: dish, portions, total time.
- Shopping list by aisle, in real pack quantities, with the budget total and
  its currency.
- Prep order: what to batch, what keeps, what to do the night before.
- Swap table: dish, likely missing ingredient, cleared substitute.
- Assumptions this plan rests on and what would change it."""

DOMAIN: DomainInfo = DomainInfo(
    id="food",
    name="Food & Nutrition Expert",
    description=(
        "Turns dietary constraints into a cookable week: allergy-cleared "
        "recipes chosen for ingredient reuse, portioned properly, with a "
        "shopping list, a prep order, and a substitute for everything."
    ),
    capabilities=(
        "Dietary constraint and allergen analysis",
        "Macro and micronutrient planning",
        "Recipe development with ingredient reuse",
        "Weekly meal planning and shopping lists",
    ),
    team=(
        SubagentSpec(
            id="requirements",
            name="Requirements Analyst",
            description="Establishes allergies first, then the other constraints.",
            role=(
                "establish the allergies and intolerances before anything "
                "else, then diet, budget, equipment, time and skill"
            ),
            instructions=_REQUIREMENTS_INSTRUCTIONS,
            output_format=_REQUIREMENTS_OUTPUT,
        ),
        SubagentSpec(
            id="nutrition",
            name="Nutrition Analyst",
            description="Sets macros, at-risk micronutrients and portions.",
            role=(
                "set the macro split, name the micronutrients this constraint "
                "set actually puts at risk, and give portions by weight"
            ),
            instructions=_NUTRITION_INSTRUCTIONS,
            output_format=_NUTRITION_OUTPUT,
        ),
        SubagentSpec(
            id="recipes",
            name="Recipe Developer",
            description="Builds dishes that clear the constraints and reuse stock.",
            role=(
                "develop concrete dishes with ingredients and method, chosen "
                "to reuse ingredients across the week"
            ),
            instructions=_RECIPES_INSTRUCTIONS,
            output_format=_RECIPES_OUTPUT,
        ),
        SubagentSpec(
            id="plan",
            name="Meal Plan Writer",
            description="Writes the plan, shopping list, prep order and swaps.",
            role=(
                "write the weekly plan with its shopping list, prep order and "
                "cleared substitutes, re-checking the allergy list last"
            ),
            instructions=_PLAN_INSTRUCTIONS,
            output_format=_PLAN_OUTPUT,
        ),
    ),
    tools=("web_search", "data_fetch", "summarize", "file_read"),
    expertise=(
        "food and nutrition planning: allergen and intolerance clearance, "
        "macro and at-risk micronutrient planning, recipe development chosen "
        "for ingredient reuse, weekly meal plans with shopping lists, prep "
        "order and substitutions"
    ),
    # Contrastive against health (clinical questions), local (restaurants in an
    # area) and general: the deliverable here is a cookable plan.
    routing_hint=(
        "cooking and eating: meal plans, recipes, shopping lists, dietary "
        "constraints and allergies, macros and portioning, what to cook this "
        "week; NOT a clinical or medical question about a condition, a "
        "medicine or a supplement, which is health, and NOT finding "
        "restaurants in an area, which is local"
    ),
    group="life",
    methodology=_METHODOLOGY,
    output_format=_OUTPUT_FORMAT,
    planning_example=_PLANNING_EXAMPLE,
    review_rubric=_REVIEW_RUBRIC,
    review_criteria=_REVIEW_CRITERIA,
    deliverable_member="plan",
)
