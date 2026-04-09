## Extracted Geometry Prompts

### Simple — single shape, ≤2 constraints

| # | Prompt |
|---|--------|
| 1 | Points A, B, C, D are on ⊙O. OA⊥BC, ∠AOB=60°, ∠ADC=30° |
| 2 | In △ABC, point D is on AB and point E is on AC. AB=AC, CD⊥AB, BE⊥AC |
| 3 | △ABC is equilateral. Points D and E lie on side BC, ∠DAE=30° |
| 4 | In △ABC, AB=AC, ∠CAB=30°. M is the midpoint of AB. N is a point on AC such that AN=NB. Connect NB. |
| 5 | In rhombus ABCD, point E lies on BD and AC. ∠DBC=60°, BD=1. F is the midpoint of BC. Connect EF, AC, BD. |
| 6 | In △ABC, AB=AC. Make AD perpendicular to BC at point D. ∠BAC=70°. |
| 7 | Given points A, B, C on ⊙O. Connect OA, AC, CB, BO. ∠AOB=100°. What is ∠ACB? |
| 8 | AB is the diameter of ⊙O. Chord CD⊥AB connects OC and BD at point E. ∠AOC=110°. |
| 9 | In rhombus ABCD, diagonals AC and BD intersect at O. OA=1, OB=2. |

---

### Medium — multi-constraint, single diagram

| # | Prompt |
|---|--------|
| 10 | In circle ⊙O, diameter AB intersects chord CD at P. Connect AC, AD, BD. ∠ACD=20°, ∠BPC=70°, ∠ADC=40°. |
| 11 | AB is the diameter of ⊙O. P is outside ⊙O. PA is tangent to ⊙O at A. C is on ⊙O. Connect PC, AC, OC. PC=PA and PC is tangent to ⊙O at C. |
| 12 | Line AB is tangent to ⊙O at B. OA intersects ⊙O at C. BD∥OA and intersects ⊙O at D. Connect CD. ∠OCD=25°, ∠OAB=40°. |
| 13 | In △ABC, AB∥CD. ∠BAC=40°. E is on the extension of AC. D is outside △ABC. ∠EDC=24°, ∠AED=16°. |
| 14 | In parallelogram ABCD, F is on the extension of BC. E is the midpoint of CD and lies on AF. ∠ACB=90°, AD=BC. Connect DF and CF. |
| 15 | In rectangle ABCD, O is on AC and BD. E is outside the rectangle. DE∥AC, CE∥BD. |
| 16 | PA is tangent to ⊙O at A. PO intersects ⊙O at C. Connect BC. ∠ABC=28°, ∠APO=34°. AB is the diameter. |
| 17 | Quadrilateral ABCD inscribed in ⊙O. Diagonal BD is the diameter. Connect OA and CA. OA⊥BD, CA bisects ∠BCD. |
| 18 | Triangle ABC inscribed in circle O. CD is the diameter of circle O. BD is connected. ∠DCA=41°, ∠ABC=49°. |
| 19 | In triangle △ABC, D is outside the triangle. ∠ABC=60°, ∠DCB=90°, ∠ADC=120°. |
| 20 | In equilateral △ABC, AD⊥BC at D. E is on AD (not A or D). Connect BE and CE. F is outside △ABC such that CE=CF and ∠ECF=60°. |
| 21 | In rectangle ABCD, E is on AB. Connect DE (the bisector of ∠ADC). F is on the extension of DE. Connect BF; ∠BFE=90°. Connect AF, CF. CF and AB intersect at G. |
| 22 | In triangle ABC, points D, E, F are the midpoints of AB, AC, BC. Connect DE, EF, DF. P, M, N are the midpoints of DE, DF, EF. Connect PM, PN, MN. |
| 23 | The equilateral triangle ABC is inscribed in circle O. D and E are on sides AC and AB. Connect OD and OE. DA=BE. |
| 24 | In △ABC, ∠ACB=90°, AD bisects ∠BAC and intersects BC at D. DE⊥AB at E. DE=1.5, BD=3. |
| 25 | In rhombus ABCD, E, F, G, H are midpoints of AB, BC, CD, DA. AB=6, ∠ABC=60°. Connect EF, FG, GH, HE. |

---

### Complex — multi-shape, multi-step construction sequences

These are the most useful for the recipe system and benchmark hard end.

| # | Prompt |
|---|--------|
| 26 | Let ABCD be a cyclic quadrilateral with circumcircle O, ∠ABC=120°, ∠CDA=60°. Extend CD beyond D to J such that DJ=AD. Extend BC beyond C to K such that CK=BC. Join AJ and KJ. Extend CB beyond B to E; join AE such that ∠AEB=90°. Let F, G, H, I be midpoints of AB, BC, CD, DA. Join FG, GH, HI, IF, FH, GI. Let FH and GI intersect at P; let BA and DC intersect at Q. Prove FGHI is a parallelogram. |
| 27 | Let ABC be inscribed in circle O with AB=BC. F is on line BC such that CF=BC. E is on ray BA beyond A such that BA=AE. G is the midpoint of AC. Join EF, EG, GF. Extend CB to H and AB to I. Join HE, HG, HI, FI. Given HI∥EF. Prove quadrilateral HIEF is an isosceles trapezoid. |
| 28 | In rhombus ABCD, diagonals AC and BD intersect at O. E is the midpoint of CD; G is the midpoint of AB. Extend OE beyond E to F such that OE=EF. Extend OG beyond G to H such that OG=GH. Prove HDBF is a parallelogram and quadrilaterals AHBO and DOCF are squares. |
| 29 | In circle O, triangle ABC is inscribed with AB=AC. Draw BE⊥AC (foot E). Draw AD⊥BC (foot D). Draw EK⊥BC (foot K). Join OE; suppose OE⊥AD. BE and AD intersect at H; AH=2·OD. G is on AD. Join BG, CG, GE. |
| 30 | In circle O, equilateral triangle ABC is inscribed and ∠ABC=90°. Chord DE lies on circle O. P is on BC. Extend BA beyond A to R; join PR, letting PR intersect AC at Q. Join BE, RE, DR, DQ with DR⊥AC. Join DP with DP⊥BC. |
| 31 | In circle O, triangle ABC is inscribed with ∠BAC=80°. KE is a diameter. Diameter AD bisects ∠BAC. F is the midpoint of BC; G is the midpoint of DK. Join DK, FG, GO, FO. Given FG=FO. |
