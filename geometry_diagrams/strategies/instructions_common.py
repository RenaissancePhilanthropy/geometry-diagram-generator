"""Prompt text shared by the generation strategies' system prompts.

A leaf module (imports nothing from the package), so every instructions_*.py
can use it without an import cycle."""

# One rule, stated once. The surrounding line format differs per prompt (a bullet
# in python_full and recipe, a numbered rule in structured), so callers add that.
ANSWER_LABEL_RULE = (
    "Label what the request gives, not what it asks you to find. A figure that accompanies a "
    "question (\"find x\", \"what is the area\", \"how long is AB\") shows the given values and names "
    "the unknown the way the request does (a variable such as x, or a \"?\"). Never write the "
    "solved value on the figure, whether as a length, an angle, an area or a volume, unless the "
    "request states that value or asks for it to be shown. \"Find\" asks the reader to work it out, "
    "not the figure to show it. A formula or worked step that ends in the result (\"Area = 12 x 5 = "
    "60\", \"AC = sqrt(6^2 + 8^2) = 10\") is the solved value too, so put no such line in any label "
    "or free text. The geometry itself may be built to satisfy the answer."
)
