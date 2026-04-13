# Student Diagram Queries — Generated from Curriculum

**201 scenarios** generated from the geometry curriculum.

## Tier 1: Basic Construction (36 scenarios)

**geo-m1-t1-l0-a1-pythagorean-distance-1** `coordinate-grid, pythagorean-theorem, right-triangle, distance`

> Can you draw a coordinate grid and plot two points — let's call them A at (1, 2) and B at (7, 6)? Then draw a right triangle by adding a third point C at (7, 2) so that AC is horizontal and BC is vertical. Label all three points, show the right angle at C, and mark the lengths of the two legs. I need to see how the hypotenuse AB connects the original two points.

Labels: A, B, C
Properties: `right_angle(A, C, B)`, `collinear(A, C, B)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `mark_present(right_angle, C)`

**geo-m1-t1-l1-a12-ray-vs-segment-1** `ray, line-segment, endpoint, notation, defined-terms`

> Please draw two separate figures side by side. In the first figure, draw ray AB — starting at endpoint A and going through B and continuing forever in that direction. In the second figure, draw line segment CD with endpoints C and D, and mark it as 4 units long. Label all points and use an arrow on the ray to show it goes on forever. I want to see the difference between a ray and a segment clearly.

Labels: A, B, C, D
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `point_on_line(B, A, B)`, `point_on_segment(C, C, D)`, `point_on_segment(D, C, D)`

**geo-m1-t1-l1-gs-points-lines-1** `points, lines, collinear, undefined-terms, naming-conventions`

> Draw a flat plane and put several labeled points on it — A, B, C, D, and E. Make points A, B, and C all sit on the same straight line and label that line with a lowercase letter like 'm'. Then put points D and E somewhere off that line so they are NOT collinear with A, B, C. Draw a second line through D and E and label it 'n'. I want to see clearly which points are collinear on line m and which ones are not.

Labels: A, B, C, D, E, m, n
Properties: `collinear(A, B, C)`, `point_on_line(A, B, C)`, `point_on_line(B, A, C)`, `point_on_line(C, A, B)`, `point_on_line(D, D, E)`, `point_on_line(E, D, E)`, `label_present(A)`, `label_present(D)`, `label_present(E)`

**geo-m1-t1-l1-tt-labeled-diagram-1** `points, lines, plane, symbolic-notation, naming`

> Draw a diagram showing a flat plane — you can draw it as a parallelogram shape and label the plane with the letter P. Put three labeled points on the plane: X, Y, and Z. Draw a line through X and Y and label it line 'l'. Make Z a separate point not on line l but still on the plane. I need to be able to name the plane, the line, and all three points from this diagram.

Labels: X, Y, Z, P, l
Properties: `point_on_line(X, X, Y)`, `point_on_line(Y, X, Y)`, `collinear(X, Y, Z)`, `label_present(X)`, `label_present(Y)`, `label_present(Z)`, `label_present(P)`

**geo-m1-t1-l3-a32-angle-addition-postulate-1** `angle-addition-postulate, interior-ray, angle, postulate`

> Draw angle ABC where A is on the upper left, B is the vertex at the bottom, and C is on the upper right. Then draw a ray BD from vertex B that goes between rays BA and BC — so D is somewhere in the interior of the angle. Label all four points A, B, C, D. Mark angle ABD as 30 degrees and angle DBC as 45 degrees, so the whole angle ABC is 75 degrees. This is the Angle Addition Postulate.

Labels: A, B, C, D
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `point_on_line(D, B, D)`, `same_side(D, A, B, C)`

**geo-m1-t1-l3-a32-angle-naming-linear-pair-1** `angle, vertex, linear-pair, supplementary, postulate`

> Draw two rays that share the same endpoint B, going in opposite directions to make a straight line. So I have point A on the left, point B in the middle, and point C on the right, all collinear. Then draw a fourth point D above B, and draw ray BD going upward from B. This creates two angles: angle ABD and angle DBC. Label all four points and mark the two angles. I want to show the linear pair postulate — that these two angles together form a straight angle of 180 degrees.

Labels: A, B, C, D
Properties: `collinear(A, B, C)`, `point_on_segment(B, A, C)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `point_on_line(D, B, D)`

**geo-m1-t1-l3-a32-segment-addition-postulate-1** `segment-addition-postulate, collinear, between, postulate`

> Draw three collinear points — A, then M in the middle, then B at the end — all on the same line segment. Label A on the far left, M between them, and B on the far right. Mark the length of AM as 3 units and MB as 5 units, so AB should be 8 units total. I want this diagram to illustrate the Segment Addition Postulate: that AM + MB = AB.

Labels: A, M, B
Properties: `collinear(A, M, B)`, `point_on_segment(M, A, B)`, `label_present(A)`, `label_present(M)`, `label_present(B)`

**geo-m1-t3-l1-gs-trapezoid-translation-1** `translation, coordinate-plane, trapezoid`

> Can you draw a coordinate plane with trapezoid ABCD where A is at (1, 1), B is at (4, 1), C is at (3, 3), and D is at (2, 3)? Then show it translated 5 units to the right as A'B'C'D', and also show it translated 3 units up as A''B''C''D''. Label all the vertices on both images and the original.

Labels: A, B, C, D, A', B', C', D', A'', B'', C'', D''
Properties: `equal_lengths(['A', "A'"], ['B', "B'"])`, `equal_lengths(['A', "A''"], ['D', "D''"])`, `label_present(A)`, `label_present(A')`, `label_present(A'')`, `equal_lengths(['A', 'B'], ["A'", "B'"])`

**geo-m1-t3-l3-act33-angle-bisector-construction-1** `angle-bisector, construction, compass-straightedge`

> Draw angle ABC where A is up and to the right, B is the vertex at the bottom middle, and C is up and to the left, making about a 60-degree angle. Then construct the angle bisector from B — draw the bisector ray BD going straight up from B between the two sides. Mark the two equal angles on either side of BD with single arc marks to show they're congruent. Label points A, B, C, and D.

Labels: A, B, C, D
Properties: `angle_bisector(D, B, A, C)`, `angle_equal(['A', 'B', 'D'], ['D', 'B', 'C'])`, `label_present(B)`, `label_present(D)`, `mark_present(arc, B)`, `point_on_line(D, B, D)`

**geo-m1-t3-l3-gs-perpendicular-bisector-RB-1** `reflection, perpendicular-bisector, construction`

> Draw a line segment from point R to point B, where R is on the left and B is on the right. Then construct the perpendicular bisector of segment RB — draw it as a vertical line crossing RB at its midpoint M. Mark the right angle where the bisector crosses RB, and mark M as the midpoint. Show that RM equals MB with tick marks.

Labels: R, B, M
Properties: `midpoint(M, R, B)`, `perpendicular(['R', 'B'], ['M', 'M'])`, `right_angle(R, M, B)`, `equal_lengths(['R', 'M'], ['M', 'B'])`, `label_present(R)`, `label_present(B)`, `label_present(M)`

**geo-m1-t3-l4-gs-rotation-function-1** `rotation, angle-of-rotation, rigid-motion`

> Draw a simple L-shaped figure (pre-image) and then show it rotated 90 degrees counterclockwise about a point E to create the image. Mark point E as the center of rotation. Draw an arc with an arrow curving from the pre-image to the image to show the 90° counterclockwise rotation. Label the center of rotation E and mark the 90° angle of rotation.

Labels: E
Properties: `label_present(E)`, `mark_present(arc, E)`, `equal_lengths(['E', 'A'], ['E', "A'"])`

**geo-m1-t4-l1-hexagon-symmetry-1** `reflectional-symmetry, rotational-symmetry, regular-polygon`

> Can you draw a regular hexagon with all 6 lines of symmetry drawn in? Label the center point O and label the vertices A, B, C, D, E, F going around. Draw the lines of symmetry as dashed lines through the center — some should go through opposite vertices and some should go through midpoints of opposite sides. I need to see all of them at once.

Labels: A, B, C, D, E, F, O
Properties: `label_present(O)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(E)`, `label_present(F)`, `collinear(A, O, D)`, `collinear(B, O, E)`, `collinear(C, O, F)`

**geo-m1-t4-l1-isosceles-trapezoid-symmetry-1** `reflectional-symmetry, isosceles-trapezoid`

> Draw an isosceles trapezoid with vertices labeled A (top-left), B (top-right), C (bottom-right), and D (bottom-left). Make AB the shorter top base and DC the longer bottom base. Show the one line of symmetry as a dashed vertical line through the midpoints of AB and DC — label those midpoints M and N. I want to see that AD equals BC and that the line MN is perpendicular to both bases.

Labels: A, B, C, D, M, N
Properties: `midpoint(M, A, B)`, `midpoint(N, D, C)`, `perpendicular(['M', 'N'], ['A', 'B'])`, `perpendicular(['M', 'N'], ['D', 'C'])`, `equal_lengths(['A', 'D'], ['B', 'C'])`, `point_on_segment(M, M, N)`, `point_on_segment(N, M, N)`

**geo-m1-t4-l1-scalene-right-triangle-symmetry-1** `rotational-symmetry, scalene-triangle, right-triangle`

> Draw a scalene right triangle with vertices A, B, and C where the right angle is at C. Make sure none of the sides are equal — like maybe AC is 3 units, BC is 4 units, and AB is 5 units. I want to show that this triangle has NO lines of symmetry and NO rotational symmetry. Can you just draw the triangle with the right angle marked at C and tick marks showing all three sides are different lengths?

Labels: A, B, C
Properties: `right_angle(A, C, B)`, `mark_present(right_angle, C)`, `mark_present(tick1, A)`, `mark_present(tick2, B)`, `label_present(A)`

**geo-m2-t1-l1-a3-inscribed-angle-semicircle-3** `circle, inscribed-angle, semicircle, diameter`

> Draw a circle with center O. Draw a diameter from A to B. Put another point C on the circle (not on the diameter). Draw lines from C to A and from C to B to form triangle CAB where C is on the circle. I want to show that angle ACB is always a right angle when it's inscribed in a semicircle. Please mark the right angle at C and label all three points.

Labels: O, A, B, C
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_segment(O, A, B)`, `right_angle(A, C, B)`, `mark_present(right_angle, C)`

**geo-m2-t1-l2-a0-convex-concave-diagonals-1** `quadrilateral, diagonal, convex, concave, vertical-angles`

> Can you draw two quadrilaterals side by side? The first one should be a convex quadrilateral ABCD (all vertices point outward) with both diagonals AC and BD drawn so they intersect inside the quadrilateral at point E. The second one should be a concave quadrilateral PQRS where one vertex (let's say R) points inward, and draw both diagonals PR and QS — show how one diagonal falls outside the shape. Label the intersection point E in the convex one and mark a pair of vertical angles at E.

Labels: A, B, C, D, E, P, Q, R, S
Properties: `point_on_segment(E, A, C)`, `point_on_segment(E, B, D)`, `angle_equal(['A', 'E', 'B'], ['C', 'E', 'D'])`, `angle_equal(['A', 'E', 'D'], ['C', 'E', 'B'])`

**geo-m2-t1-l3-a4-equilateral-triangle-compass-1** `equilateral-triangle, compass-construction, equal-sides`

> Show me how to construct an equilateral triangle with compass and straightedge starting from a segment AB that is 6 units long. Draw segment AB. Then draw two arcs: one centered at A with radius AB and one centered at B with radius AB. Label the intersection of those arcs as point C. Connect A to C and B to C. Mark all three sides as equal with tick marks and label all three vertices A, B, C.

Labels: A, B, C
Properties: `equal_lengths(['A', 'B'], ['B', 'C'], ['A', 'C'])`, `mark_present(tick, A)`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m2-t1-l4-a1-isosceles-base-angles-1** `triangle, isosceles, base-angles, congruent`

> Draw an isosceles triangle ABC where AB equals AC (the two equal sides meet at vertex A). Mark the two equal sides AB and AC with tick marks. The base is BC. I want to show the base angles conjecture: that angle B equals angle C. Mark those two base angles as equal with arc marks. Label all three vertices.

Labels: A, B, C
Properties: `equal_lengths(['A', 'B'], ['A', 'C'])`, `angle_equal(['A', 'B', 'C'], ['A', 'C', 'B'])`, `mark_present(tick, A)`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m2-t1-l5-a0-concurrent-lines-circle-1** `circle, concurrent-lines, point-of-concurrency, inscribed-triangle`

> Draw a circle with center O. Place three points on the circle to make triangle ABC. Then draw three lines, each passing through the center O and one vertex of the triangle — so draw line through O and A, line through O and B, and line through O and C. All three lines meet at O. Label all four points A, B, C, O and note that O is the point of concurrency. I want to see clearly that OA, OB, and OC are all equal (they're radii).

Labels: O, A, B, C
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `equal_lengths(['O', 'A'], ['O', 'B'], ['O', 'C'])`, `point_on_line(O, A, O)`, `label_present(O)`

**geo-m2-t2-l1-a11-segment-collinear-1** `collinear-points, segment-addition, reflexive-property`

> Draw three collinear points A, M, and B in that order on a line segment where M is the midpoint of AB. Label the segment from A to M as 5 units and from M to B as 5 units. I want to use this to illustrate the segment addition postulate where AM + MB = AB.

Labels: A, M, B
Properties: `point_on_segment(M, A, B)`, `midpoint(M, A, B)`, `equal_lengths(['A', 'M'], ['M', 'B'])`

**geo-m2-t2-l1-a12-right-angle-congruence-1** `right-angle, congruence, flow-chart-proof`

> Draw two separate right angles. Label the first one as angle ABC where B is the vertex, and the second one as angle DEF where E is the vertex. Put a small square at each vertex to show they're right angles, and put a single congruence arc on each angle to show that angle ABC is congruent to angle DEF. I'm proving the right angle congruence postulate.

Labels: A, B, C, D, E, F
Properties: `right_angle(A, B, C)`, `right_angle(D, E, F)`, `angle_equal(['A', 'B', 'C'], ['D', 'E', 'F'])`

**geo-m2-t2-l1-gs-vertical-angles-1** `vertical-angles, intersecting-lines, supplementary-angles`

> Can you draw two lines intersecting at a point O? Label the four angles as angle 1, angle 2, angle 3, and angle 4 going around the intersection. I want to see which angles are vertical pairs and which ones form linear pairs. Mark angles 1 and 3 with one tick mark to show they're equal, and mark angles 2 and 4 with two tick marks to show they're equal.

Labels: O, 1, 2, 3, 4
Properties: `angle_equal(['2', 'O', '4'], ['1', 'O', '3'])`, `mark_present(tick, 1)`, `mark_present(tick, 3)`

**geo-m2-t2-l2-gs-parallel-transversal-1** `parallel-lines, transversal, corresponding-angles, alternate-interior-angles`

> Draw two horizontal parallel lines — call them line m and line n — cut by a diagonal transversal line t. Label the intersection points: where t meets m call it point P, and where t meets n call it point Q. Number all eight angles formed: angles 1, 2, 3, 4 at point P (going clockwise from upper-left) and angles 5, 6, 7, 8 at point Q (going clockwise from upper-left). Mark the parallel lines with arrows to show they're parallel.

Labels: m, n, t, P, Q, 1, 2, 3, 4, 5, 6, 7, 8
Properties: `parallel(['P', 'm_end'], ['Q', 'n_end'])`, `angle_equal(['ref1', 'P', 'ref2'], ['ref3', 'Q', 'ref4'])`

**geo-m2-t2-l6-gs-clock-arcs-1** `circle, arc-measure, central-angle, arc-addition-postulate`

> Draw a circle with center O representing a clock face. Mark 12 points on the circle for the clock hours and label them 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11. Draw radii from O to the 12 and to the 4. Label the central angle between those two radii. Shade the minor arc from 12 to 4 and label it with its degree measure (120°). Also draw the radius to 8 and shade the arc from 4 to 8, labeling it 120° too, to illustrate the arc addition postulate.

Labels: O, 12, 4, 8
Properties: `point_on_circle(12, O, 4)`, `point_on_circle(4, O, 12)`, `point_on_circle(8, O, 12)`

**geo-m2-t3-l1-gs-right-triangle-hl-construction-1** `right-triangle, HL, construction, hypotenuse, leg`

> Can you draw a right triangle called triangle ABC where the right angle is at C? Make side AC (one leg) 6 units long and the hypotenuse AB 10 units long. Label all three vertices A, B, and C, mark the right angle at C with a little square, and label the lengths of AC and AB. I want to see what a right triangle looks like when you're only given a leg and the hypotenuse.

Labels: A, B, C
Properties: `right_angle(A, C, B)`, `mark_present(right_angle, C)`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m2-t3-l3-gs-quadrilateral-hierarchy-1** `quadrilateral, hierarchy, parallelogram, rhombus, rectangle, square, trapezoid, kite`

> Draw six separate quadrilateral figures and label each one clearly. I need: (1) a general quadrilateral ABCD with no special marks, (2) a trapezoid TRAP with exactly one pair of parallel sides — mark those parallel sides with arrows, (3) a parallelogram PARM with both pairs of opposite sides parallel — mark all parallel sides, (4) a rhombus RHOM with all four sides equal — mark all sides with tick marks, (5) a rectangle RECT with four right angles — mark all corners with squares, and (6) a square SQRE with four equal sides AND four right angles — mark both. I want to use these to make a flow chart showing how each shape relates to the others.

Labels: A, B, C, D, T, R, P, H, O, M, E, S, Q
Properties: `parallel(['T', 'R'], ['A', 'P'])`, `parallel(['P', 'A'], ['R', 'M'])`, `parallel(['P', 'R'], ['A', 'M'])`, `equal_lengths(['R', 'H'], ['H', 'O'], ['O', 'M'], ['M', 'R'])`, `right_angle(R, E, C)`, `equal_lengths(['S', 'Q'], ['Q', 'R'], ['R', 'E'], ['E', 'S'])`

**geo-m3-t1-l3-act33-angle-bisector-application-1** `angle-bisector, proportional-sides, unknown-length`

> Draw triangle XYZ where the angle bisector from angle Y hits side XZ at point W. Label the sides XY = 8, YZ = 12, and XW = 6. I need to find WZ. Show the proportion XW/WZ = XY/YZ on the diagram and mark the angle bisector clearly. Leave WZ labeled with a question mark or the variable 'a' so I can see what I'm solving for.

Labels: X, Y, Z, W
Properties: `angle_bisector(W, Y, X, Z)`, `point_on_segment(W, X, Z)`, `label_present(W)`, `label_present(X)`, `label_present(Y)`, `label_present(Z)`

**geo-m4-t1-l1-gs-intersecting-chords-1** `circles, chords, intersecting-chords`

> Can you draw a circle with two chords that cross each other inside the circle? Label the point where they intersect as P. Call the chords AE and BD so they cross at P. Then label the four segments AP, PE, BP, and PD with their lengths — like AP = 3, PE = 8, BP = 4, PD = 6 — so I can see that AP times PE equals BP times PD.

Labels: A, B, D, E, P
Properties: `point_on_segment(P, A, E)`, `point_on_segment(P, B, D)`, `label_present(A)`, `label_present(E)`, `label_present(B)`, `label_present(D)`, `label_present(P)`

**geo-m4-t1-l2-talktalk-ferris-wheel-1** `circles, arc-length, sectors, real-world`

> Draw a circle representing a Ferris wheel with center O and radius labeled 50 ft. Divide the circle into 18 equal sectors — like slices of a pie — by drawing 18 radii evenly spaced. Label two adjacent radii as OA and OB and shade the arc AB between them. I need to find the arc length of that one steel arc, so label the central angle for one sector as 20 degrees (since 360 ÷ 18 = 20).

Labels: O, A, B
Properties: `label_present(O)`, `label_present(A)`, `label_present(B)`, `equal_lengths(['O', 'A'], ['O', 'B'])`

**geo-m4-t1-l4-act41-circles-on-coordinate-plane-1** `circles, coordinate-geometry, standard-form, graphing`

> Draw four separate coordinate planes, each with a circle on it. Circle 1: centered at origin O with radius 4. Circle 2: centered at (3, −5) with radius 3. Circle 3: centered at (−5, 0) with radius 6. Circle 4: centered at (0, −2) with radius 5. Label each center point and write the radius next to each circle. I need to practice writing the equation for each one.

Labels: O
Properties: `label_present(O)`

**geo-m4-t1-l5-gs-radar-circle-axis-points-1** `circles, coordinate-geometry, points-on-circle, symmetry`

> Draw a coordinate plane with a circle centered at the origin O and radius 10. Mark and label the four points where the circle crosses the axes: A = (10, 0), B = (0, 10), C = (−10, 0), and D = (0, −10). These represent objects on a radar screen. Label all four points and the center O, and label the radius as 10.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, A)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `equal_lengths(['O', 'A'], ['O', 'B'], ['O', 'C'], ['O', 'D'])`, `label_present(O)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m4-t2-l1-gs-disc-definition-2** `rotation, disc, circle, 2d-to-3d`

> Draw a circle with center O and radius r labeled. Then next to it draw a filled-in disc (a solid circle) with the same center O and radius r. Label the disc and show that it has area π times r squared. I'm trying to understand the difference between just the outline of a circle and a fully filled disc.

Labels: O, r
Properties: `label_present(O)`, `label_present(r)`, `mark_present(radius, O)`

**geo-m4-t2-l2-a22-sphere-cross-sections-1** `cross-section, sphere, great-circle, circle`

> Draw two spheres with center O and radius r. On the first sphere, draw a plane passing directly through center O to create a great circle cross-section — shade the great circle, label its center O, and mark the radius r. On the second sphere, draw a plane cutting through the sphere but NOT through the center to create a smaller circular cross-section — shade that smaller circle and label it to show its radius is less than r. Label both spheres with center O and radius r.

Labels: O, r
Properties: `label_present(O)`, `label_present(r)`, `point_on_circle(O, O, r_point)`, `mark_present(radius, O)`

**geo-m4-t2-l3-a33-sphere-labeled-1** `sphere, hemisphere, radius, diameter, volume`

> Draw a sphere with center O. Draw and label the radius r from O to a point P on the surface, and the diameter d = 2r as a straight line through O from point A to point B on opposite sides of the sphere. Draw a dashed great circle (equator) around the middle of the sphere. Next to the sphere, draw a hemisphere (the top half) with the flat circular base showing — label the radius r on the flat base and mark the center O. Label the volume formulas: V = (4/3)πr³ for the sphere and V = (2/3)πr³ for the hemisphere.

Labels: O, r, d, A, B, P
Properties: `label_present(O)`, `label_present(r)`, `label_present(A)`, `label_present(B)`, `label_present(P)`, `point_on_segment(O, A, B)`, `point_on_circle(P, O, P)`, `equal_lengths(['O', 'A'], ['O', 'B'], ['O', 'P'])`

**geo-m4-t2-l3-tt-volume-summary-1** `volume, prism, pyramid, cylinder, cone, sphere, summary`

> Draw a summary diagram showing one labeled example of each of these 5 solids side by side: (1) a rectangular prism with base B and height h labeled, (2) a cylinder with radius r and height h labeled, (3) a square pyramid with base side s and height h labeled, (4) a cone with radius r and height h labeled, (5) a sphere with radius r labeled. Under each solid write its volume formula: Bh, πr²h, (1/3)s²h, (1/3)πr²h, and (4/3)πr³ respectively. I want this as a reference sheet.

Labels: r, h, s, B
Properties: `label_present(r)`, `label_present(h)`, `label_present(s)`, `label_present(B)`

**geo-m4-t2-l4-a42-sphere-surface-area-1** `sphere, hemisphere, surface-area, great-circle`

> Draw a sphere with center O and radius r labeled. Next to it, draw a hemisphere (flat side facing right) with center O and radius r labeled. On the hemisphere, mark the curved surface on top (lateral surface area = 2πr²) and the flat circular base (area = πr²). Draw a dashed line showing the great circle that forms the flat base of the hemisphere. Label the total surface area of the full sphere as SA = 4πr² and the total surface area of the hemisphere as SA = 3πr² (2πr² curved + πr² flat base).

Labels: O, r
Properties: `label_present(O)`, `label_present(r)`, `point_on_circle(r_point, O, r_point)`, `equal_lengths(['O', 'P1'], ['O', 'P2'])`

## Tier 2: Theorem / Proof Diagram (128 scenarios)

**geo-m1-t1-l1-a12-congruent-segments-triangle-1** `congruent-segments, tick-marks, isosceles-triangle, equilateral-triangle`

> Draw two triangles next to each other. The first one is triangle ABC where sides AB and AC are the same length — mark them both with a single tick mark to show they're congruent. This is an isosceles triangle. The second one is triangle DEF where all three sides DE, EF, and FD are the same length — mark them all with double tick marks to show they're all congruent. Label all six vertices.

Labels: A, B, C, D, E, F
Properties: `equal_lengths(['A', 'B'], ['A', 'C'])`, `equal_lengths(['D', 'E'], ['E', 'F'], ['F', 'D'])`, `mark_present(tick, A)`, `mark_present(tick, C)`, `label_present(A)`, `label_present(D)`, `label_present(E)`, `label_present(F)`

**geo-m1-t1-l1-gs-points-lines-2** `lines, intersection, collinear, naming-conventions`

> I need a diagram with two straight lines that cross each other at a point. Label the intersection point P. On the first line, put points A and B on either side of P. On the second line, put points C and D on either side of P. Make sure P is clearly between A and B, and also between C and D. Label all five points. I want to see that P is the intersection of line AB and line CD.

Labels: A, B, C, D, P
Properties: `point_on_segment(P, A, B)`, `point_on_segment(P, C, D)`, `intersects(A, B, P)`, `collinear(A, P, B)`, `collinear(C, P, D)`, `label_present(P)`

**geo-m1-t1-l2-a21-conditional-midpoint-1** `conditional-statement, midpoint, congruent-segments, collinear, counterexample`

> I need a diagram to show a counterexample to the conditional: 'If M is a point where AM = MB, then M is the midpoint of segment AB.' Draw point A and point B connected by a segment. Then draw point M somewhere NOT on segment AB — like off to the side — but make AM and MB the same length. Mark the equal lengths with tick marks. Label all three points. This shows M can be equidistant from A and B without being the midpoint of AB.

Labels: A, B, M
Properties: `equal_lengths(['A', 'M'], ['M', 'B'])`, `not_between(M, A, B)`, `mark_present(tick, M)`, `label_present(A)`, `label_present(B)`, `label_present(M)`

**geo-m1-t1-l3-a33-three-squares-diagonals-1** `diagonal, adjacent-squares, angle-sum, conjecture, protractor`

> Draw three squares placed side by side horizontally so they share sides — like a 1×3 strip of squares. Label the top-left corner of the first square as A. Label the bottom-right corner of the first square as P, the bottom-right corner of the second square as Q, and the bottom-right corner of the third square as R. Draw three line segments: from A to P, from A to Q, and from A to R. Label the three angles formed between these segments as angle a (between AP and AQ), angle b (between AQ and AR... wait, let me re-think) — actually label angle a between the left side of the first square and segment AP, angle b between AP and AQ, and angle c between AQ and AR. I want to see that angles a + b + c = 90 degrees.

Labels: A, P, Q, R
Properties: `label_present(A)`, `label_present(P)`, `label_present(Q)`, `label_present(R)`, `point_on_segment(P, A, P)`, `point_on_segment(Q, A, Q)`, `point_on_segment(R, A, R)`

**geo-m1-t3-l1-act11-triangle-translation-directed-segment-1** `translation, directed-line-segment, triangle, coordinate-plane`

> I need a diagram showing triangle PQR with P at (1, 2), Q at (3, 2), and R at (2, 4) on a coordinate plane. Draw a directed line segment from P going 4 units right and 2 units up, with an arrow at the tip showing the direction of translation. Then draw the translated triangle P'Q'R' in its new position. Label all six vertices and show the directed line segment clearly.

Labels: P, Q, R, P', Q', R'
Properties: `label_present(P)`, `label_present(P')`, `equal_lengths(['P', 'Q'], ["P'", "Q'"])`, `equal_lengths(['Q', 'R'], ["Q'", "R'"])`, `parallel(['P', "P'"], ['Q', "Q'"])`, `parallel(['Q', "Q'"], ['R', "R'"])`

**geo-m1-t3-l1-act12-dilation-vs-translation-1** `translation, dilation, rigid-motion, congruence`

> Draw two diagrams side by side. In the first, show triangle ABC with A at (0,0), B at (3,0), C at (1,2), and its translated image A'B'C' shifted 4 units right so A' is at (4,0). In the second diagram, show the same triangle ABC but this time show a dilated (non-congruent) image A''B''C'' where every coordinate is doubled, so A'' is at (0,0), B'' is at (6,0), C'' is at (2,4). Label all vertices in both diagrams so I can see why one is a rigid motion and the other isn't.

Labels: A, B, C, A', B', C', A'', B'', C''
Properties: `equal_lengths(['A', 'B'], ["A'", "B'"])`, `equal_lengths(["A''", "B''"], ['A', 'C'])`, `label_present(A)`, `label_present(A'')`, `parallel(['A', "A'"], ['B', "B'"])`

**geo-m1-t3-l2-act21-sequence-triangle-translations-1** `translation, sequence-of-transformations, coordinate-notation, congruence`

> Show me triangle DEF on a coordinate plane with D at (0,0), E at (3,0), F at (1,2). Then show the result after first translating it 2 units right to get D'E'F', then translating that result 3 units up to get D''E''F''. Label all nine vertices and use arrows to show the direction of each translation step.

Labels: D, E, F, D', E', F', D'', E'', F''
Properties: `equal_lengths(['D', 'E'], ["D'", "E'"])`, `equal_lengths(['D', 'E'], ["D''", "E''"])`, `parallel(['D', "D'"], ['E', "E'"])`, `parallel(["D'", "D''"], ["E'", "E''"])`, `label_present(D'')`

**geo-m1-t3-l2-gs-trapezoid-sequence-translations-1** `translation, sequence-of-transformations, pythagorean-theorem, coordinate-plane`

> Draw trapezoid ABCD on a coordinate plane with A at (1,1), B at (4,1), C at (3,3), D at (2,3). Then draw its translated image A'B'C'D' where A' is at (4,4), showing the translation as a diagonal directed line segment from A to A'. Also draw a right triangle using the horizontal and vertical components of that directed line segment — a horizontal leg of 3 units and a vertical leg of 3 units — to show how the diagonal distance relates to the Pythagorean Theorem. Label the legs 3 and 3 and the hypotenuse with its length.

Labels: A, B, C, D, A', B', C', D'
Properties: `label_present(A)`, `label_present(A')`, `equal_lengths(['A', 'B'], ["A'", "B'"])`, `parallel(['A', "A'"], ['B', "B'"])`, `right_angle(A, A, A')`

**geo-m1-t3-l3-act31-reflection-coordinate-plane-1** `reflection, coordinate-plane, trapezoid`

> Draw a coordinate plane with trapezoid ABCD where A is at (1,2), B is at (4,2), C is at (3,4), D is at (2,4). Reflect the trapezoid across the y-axis and label the image A'B'C'D'. Then reflect the original ABCD across the x-axis and label that image A''B''C''D''. Label all twelve vertices and draw tick marks showing equal distances from each axis for corresponding points.

Labels: A, B, C, D, A', B', C', D', A'', B'', C'', D''
Properties: `equal_lengths(['A', "A'"], ['A', "A'"])`, `equal_lengths(['A', 'B'], ["A'", "B'"])`, `equal_lengths(['A', 'B'], ["A''", "B''"])`, `label_present(A')`, `label_present(A'')`, `perpendicular(['A', "A'"], ['C', 'D'])`

**geo-m1-t3-l3-act32-reflection-function-triangles-1** `reflection, line-of-reflection, perpendicular-bisector`

> Draw triangle PQR with P at (1,3), Q at (3,1), R at (3,4). Draw a diagonal line m going from the bottom-left to the upper-right of the diagram. Reflect triangle PQR across line m to get triangle P'Q'R'. Draw dashed segments connecting P to P', Q to Q', and R to R', and mark where those dashed segments cross line m as the midpoints. Show with right-angle marks that line m is perpendicular to each dashed connector segment. Label all vertices and the line m.

Labels: P, Q, R, P', Q', R', m
Properties: `perpendicular(['P', "P'"], ['Q', "Q'"])`, `point_on_line(M, P, P')`, `equal_lengths(['P', 'Q'], ["P'", "Q'"])`, `label_present(m)`, `label_present(P')`, `equal_lengths(['P', 'M'], ['M', "P'"])`

**geo-m1-t3-l3-act34-perpendicular-bisector-theorem-1** `perpendicular-bisector-theorem, equidistant, proof`

> Draw segment RB horizontally with R on the left and B on the right. Construct the perpendicular bisector of RB, crossing at midpoint M. Place a point P somewhere on the perpendicular bisector above M. Draw segments PR and PB with dashed lines. Mark RM equal to MB with tick marks. Mark PM as a shared segment. I want this to look like a proof diagram showing that P is equidistant from R and B because it's on the perpendicular bisector. Label points R, B, M, and P.

Labels: R, B, M, P
Properties: `midpoint(M, R, B)`, `right_angle(P, M, R)`, `right_angle(P, M, B)`, `equal_lengths(['R', 'M'], ['M', 'B'])`, `equal_lengths(['P', 'R'], ['P', 'B'])`, `point_on_line(P, M, P)`, `label_present(P)`

**geo-m1-t3-l4-act41-trapezoid-rotation-coordinate-plane-1** `rotation, coordinate-plane, trapezoid, 90-degrees`

> Draw a coordinate plane and put trapezoid ABCD on it with A at (1,1), B at (3,1), C at (2,3), D at (1,3). Then rotate the whole trapezoid 90 degrees counterclockwise about the origin and label the image A'B'C'D'. Then rotate the original 180 degrees counterclockwise about the origin and label that image A''B''C''D''. Label all twelve vertices and mark the origin O.

Labels: A, B, C, D, A', B', C', D', A'', B'', C'', D'', O
Properties: `equal_lengths(['A', 'B'], ["A'", "B'"])`, `equal_lengths(['A', 'B'], ["A''", "B''"])`, `equal_lengths(['A', 'O'], ["A'", 'O'])`, `label_present(O)`, `label_present(A')`, `label_present(A'')`, `equal_lengths(['A', 'O'], ["A''", 'O'])`

**geo-m1-t3-l4-act42-concentric-circles-rotation-1** `rotation, concentric-circles, central-angle`

> Draw three concentric circles all centered at point E. Place triangle PQR so that vertex P is on the smallest circle, vertex Q is on the middle circle, and vertex R is on the largest circle. Then rotate the triangle about E by 65 degrees counterclockwise to get triangle P'Q'R'. Draw the angle of rotation for each vertex — arcs from P to P', Q to Q', and R to R' — and mark the 65° central angle at E. Label E, P, Q, R, P', Q', R'.

Labels: E, P, Q, R, P', Q', R'
Properties: `point_on_circle(P, E, P)`, `point_on_circle(P', E, P)`, `point_on_circle(Q, E, Q)`, `point_on_circle(Q', E, Q)`, `equal_lengths(['E', 'P'], ['E', "P'"])`, `equal_lengths(['E', 'Q'], ['E', "Q'"])`, `equal_lengths(['P', 'Q'], ["P'", "Q'"])`, `label_present(E)`

**geo-m1-t3-l4-ttt-270-rotation-triangle-1** `rotation, 270-degrees, coordinate-plane, coordinate-notation`

> Draw a coordinate plane and place triangle JKL with J at (2,1), K at (5,1), and L at (3,4). Rotate the triangle 270 degrees counterclockwise about the origin to get triangle J'K'L'. Draw the image and label all six vertices. Also draw arcs at the origin showing the 270° rotation. Mark the origin O.

Labels: J, K, L, J', K', L', O
Properties: `equal_lengths(['J', 'K'], ["J'", "K'"])`, `equal_lengths(['O', 'J'], ['O', "J'"])`, `equal_lengths(['O', 'K'], ['O', "K'"])`, `label_present(J')`, `label_present(O)`, `mark_present(arc, O)`

**geo-m1-t4-l1-equilateral-triangle-symmetry-1** `reflectional-symmetry, rotational-symmetry, equilateral-triangle`

> Draw an equilateral triangle with vertices labeled A (top), B (bottom-left), and C (bottom-right). Label the midpoints of each side: M on AB, N on BC, and P on AC. Then draw all 3 lines of symmetry as dashed lines — one from vertex A down to midpoint N, one from vertex B to midpoint P, and one from vertex C to midpoint M. All three dashed lines should meet at the center point labeled O. Mark all three sides as equal with tick marks.

Labels: A, B, C, M, N, P, O
Properties: `equal_lengths(['A', 'B'], ['B', 'C'], ['A', 'C'])`, `midpoint(M, A, B)`, `midpoint(N, B, C)`, `midpoint(P, A, C)`, `collinear(A, O, N)`, `collinear(B, O, P)`, `collinear(C, O, M)`, `mark_present(tick1, A)`

**geo-m1-t4-l1-square-symmetry-1** `reflectional-symmetry, rotational-symmetry, square`

> Draw a square with vertices A (top-left), B (top-right), C (bottom-right), D (bottom-left) and center point O. I need to see all 4 lines of symmetry drawn as dashed lines: one horizontal through the midpoints of AD and BC (label those midpoints M and N), one vertical through midpoints of AB and DC (label those P and Q), and two diagonal ones from A to C and from B to D. All four dashed lines should pass through the center O. Mark all four sides equal with tick marks.

Labels: A, B, C, D, O, M, N, P, Q
Properties: `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['A', 'D'])`, `midpoint(M, A, D)`, `midpoint(N, B, C)`, `midpoint(P, A, B)`, `midpoint(Q, D, C)`, `collinear(M, O, N)`, `collinear(P, O, Q)`, `collinear(A, O, C)`, `collinear(B, O, D)`

**geo-m1-t4-l2-aaa-counterexample-1** `AAA, counterexample, non-congruence, similar-triangles`

> Draw two equilateral triangles that are clearly NOT the same size to show that AAA is not a congruence theorem. Label the smaller one PQR with each side being 3 cm, and the bigger one STU with each side being 6 cm. Mark all angles in both triangles as 60 degrees. Show tick marks indicating all sides of each triangle are equal within each triangle, but use different tick marks for the two triangles to show the side lengths are different. Put them side by side.

Labels: P, Q, R, S, T, U
Properties: `equal_lengths(['P', 'Q'], ['Q', 'R'], ['P', 'R'])`, `equal_lengths(['S', 'T'], ['T', 'U'], ['S', 'U'])`, `angle_equal(['Q', 'P', 'R'], ['T', 'S', 'U'])`, `angle_equal(['P', 'Q', 'R'], ['S', 'T', 'U'])`, `angle_equal(['P', 'R', 'Q'], ['S', 'U', 'T'])`, `label_present(P)`, `label_present(S)`

**geo-m1-t4-l2-aas-congruence-1** `AAS, congruence`

> Draw two triangles to illustrate the AAS congruence theorem. Label the first one JKL and the second one XYZ. Mark angle J = angle X with one arc each, angle K = angle Y with two arcs each, and the non-included side KL = YZ with one tick mark each. Note that KL and YZ are NOT between the two marked angles — they're opposite angle J and angle X respectively. Label all six vertices clearly.

Labels: J, K, L, X, Y, Z
Properties: `angle_equal(['K', 'J', 'L'], ['Y', 'X', 'Z'])`, `angle_equal(['J', 'K', 'L'], ['X', 'Y', 'Z'])`, `equal_lengths(['K', 'L'], ['Y', 'Z'])`, `label_present(J)`, `label_present(L)`, `label_present(X)`, `label_present(Z)`

**geo-m1-t4-l2-asa-congruence-1** `ASA, congruence, included-side`

> Draw two triangles FGH and PQR to illustrate ASA congruence. Mark angle F = angle P with one arc each, side FG = side PQ with one tick mark each (that's the included side between the two angles), and angle G = angle Q with two arcs each. Label all six vertices. Make sure FG and PQ are clearly the sides between the two marked angles in each triangle.

Labels: F, G, H, P, Q, R
Properties: `equal_lengths(['F', 'G'], ['P', 'Q'])`, `angle_equal(['H', 'F', 'G'], ['R', 'P', 'Q'])`, `angle_equal(['F', 'G', 'H'], ['P', 'Q', 'R'])`, `label_present(F)`, `label_present(G)`, `label_present(H)`, `label_present(P)`, `label_present(Q)`, `label_present(R)`

**geo-m1-t4-l2-ha-congruence-1** `HA, right-triangle, congruence`

> Draw two right triangles to show the Hypotenuse-Angle (HA) congruence theorem. Label the first triangle ABC with the right angle at C, and the second triangle DEF with the right angle at F. Mark the right angles at C and F with small squares. Show that hypotenuse AB = hypotenuse DE with one tick mark each, and that angle A = angle D with one arc each. Label all six vertices.

Labels: A, B, C, D, E, F
Properties: `right_angle(A, C, B)`, `right_angle(D, F, E)`, `mark_present(right_angle, C)`, `mark_present(right_angle, F)`, `equal_lengths(['A', 'B'], ['D', 'E'])`, `angle_equal(['B', 'A', 'C'], ['E', 'D', 'F'])`

**geo-m1-t4-l2-perpendicular-bisector-reflection-1** `reflection, perpendicular-bisector, congruent-segments`

> Draw two separate congruent segments: segment AB that is horizontal and segment CD that is tilted at an angle. Then draw the perpendicular bisector of AB and label it line l, with the midpoint of AB labeled M. Show that a reflection across line l maps A to B and B to A. Mark the two equal halves AM and MB with tick marks. Also label a point X on line l and show with dashed lines that XA equals XB.

Labels: A, B, C, D, M, X, l
Properties: `midpoint(M, A, B)`, `perpendicular(['M', 'X'], ['A', 'B'])`, `point_on_line(M, M, X)`, `point_on_line(X, M, X)`, `equal_lengths(['A', 'M'], ['M', 'B'])`, `equal_lengths(['X', 'A'], ['X', 'B'])`, `equal_lengths(['A', 'B'], ['C', 'D'])`

**geo-m1-t4-l2-sss-congruence-triangles-1** `SSS, congruence, CPCTC`

> Draw two triangles side by side: triangle VAR and triangle BKF. Mark them so that VA = BK (one tick mark each), AR = KF (two tick marks each), and VR = BF (three tick marks each). Label all 6 vertices clearly. I also need the corresponding angles marked with arc marks — angle V = angle B (one arc each), angle A = angle K (two arcs each), and angle R = angle F (three arcs each). This is to show SSS congruence.

Labels: V, A, R, B, K, F
Properties: `equal_lengths(['V', 'A'], ['B', 'K'])`, `equal_lengths(['A', 'R'], ['K', 'F'])`, `equal_lengths(['V', 'R'], ['B', 'F'])`, `angle_equal(['A', 'V', 'R'], ['K', 'B', 'F'])`, `angle_equal(['V', 'A', 'R'], ['B', 'K', 'F'])`, `angle_equal(['V', 'R', 'A'], ['B', 'F', 'K'])`, `label_present(V)`, `label_present(K)`

**geo-m1-t4-l2-sss-construction-1** `SSS, triangle-construction, compass-straightedge`

> Draw three separate line segments: segment PQ with length 5 cm, segment RS with length 7 cm, and segment TU with length 4 cm. Then below those, show a finished triangle ABC that was constructed using those three lengths, where AB = 7 cm, BC = 4 cm, and AC = 5 cm. Mark the sides with tick marks to show which sides match which original segments. Label all points.

Labels: P, Q, R, S, T, U, A, B, C
Properties: `equal_lengths(['A', 'B'], ['R', 'S'])`, `equal_lengths(['B', 'C'], ['T', 'U'])`, `equal_lengths(['A', 'C'], ['P', 'Q'])`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m2-t1-l1-a1-circle-parts-bisectors-1** `circle, diameter, perpendicular-bisector, chord, central-angle`

> Can you draw a circle with center O? Put a diameter going from point A to point B through the center. Then draw the perpendicular bisector of AB — it should be another diameter, going from point C to point D, so that AB and CD cross at O at a right angle. Now draw a chord from A to C. Label all the radii (OA, OB, OC, OD), mark the right angle at O, and shade or label one of the minor arcs and one of the major arcs. I want to see how this creates an isosceles right triangle with vertices A, O, and C.

Labels: O, A, B, C, D
Properties: `point_on_segment(O, A, B)`, `point_on_segment(O, C, D)`, `perpendicular(['A', 'B'], ['C', 'D'])`, `right_angle(A, O, C)`, `equal_lengths(['O', 'A'], ['O', 'C'])`, `point_on_circle(A, O, B)`, `point_on_circle(C, O, B)`, `mark_present(right_angle, O)`

**geo-m2-t1-l1-a2-parallel-lines-circle-2** `circle, parallel-lines, transversal, corresponding-angles, alternate-interior-angles`

> Draw a circle with center O. Draw a diameter from point A to point B (this acts like a transversal). Now draw a secant line through point A that goes as a chord across the circle — call it line AC where C is on the circle. Then draw a line through O that is parallel to AC — this parallel line hits the circle at points D and E. I want to see the corresponding angles and alternate interior angles that are formed where the diameter AB crosses the two parallel lines AC and DE. Label all the points and mark the equal angle pairs.

Labels: O, A, B, C, D, E
Properties: `parallel(['A', 'C'], ['D', 'E'])`, `point_on_segment(O, D, E)`, `point_on_segment(O, A, B)`, `point_on_circle(A, O, B)`, `point_on_circle(C, O, B)`, `point_on_circle(D, O, B)`, `point_on_circle(E, O, B)`

**geo-m2-t1-l1-a2-vertical-angles-circle-1** `circle, vertical-angles, intersecting-diameters, arc-measure`

> Draw a circle with center O. Draw two diameters that cross at O — one from point A to point B, and another from point C to point D, but this time they're NOT perpendicular, so the angles they form are NOT all 90 degrees. Label the four angles at O: let's say angle AOC is 70 degrees, and then label angle COB, angle BOD, and angle DOA based on what vertical angles and supplementary angles tell us. I want to see clearly that vertical angles (like AOC and BOD) are equal and that adjacent angles add to 180 degrees.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_segment(O, A, B)`, `point_on_segment(O, C, D)`, `angle_equal(['A', 'O', 'C'], ['B', 'O', 'D'])`, `angle_equal(['C', 'O', 'B'], ['D', 'O', 'A'])`

**geo-m2-t1-l1-a3-inscribed-angle-central-angle-1** `circle, inscribed-angle, central-angle, intercepted-arc`

> Draw a circle with center O. Put three points on the circle: A, B, and C. Draw the central angle BOC (so draw radii OB and OC). Also draw the inscribed angle BAC, where A is on the circle and the angle opens toward the arc BC that doesn't contain A. Label the intercepted arc BC and mark both the central angle at O and the inscribed angle at A. I want to conjecture that the inscribed angle is half the central angle, so if the central angle BOC is 80 degrees, label the inscribed angle BAC as 40 degrees.

Labels: O, A, B, C
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `equal_lengths(['O', 'B'], ['O', 'C'])`, `angle_equal(['B', 'A', 'C'], ['B', 'A', 'C'])`

**geo-m2-t1-l1-a3-tangent-radius-perpendicular-2** `circle, tangent, radius, perpendicular, tangent-radius`

> Draw a circle with center O and a point P on the circle. Draw the radius OP. Then draw a tangent line to the circle at point P — it should just touch the circle at P and not cross it. Label the tangent line with two points on it, like T and P and S (so the tangent is line TPS). I want to show that the radius OP is perpendicular to the tangent line at P. Please mark the right angle between OP and the tangent line at P.

Labels: O, P, T, S
Properties: `point_on_circle(P, O, P)`, `tangent(['T', 'S'], O, P)`, `perpendicular(['O', 'P'], ['T', 'S'])`, `right_angle(O, P, T)`, `mark_present(right_angle, P)`

**geo-m2-t1-l2-a1-isosceles-trapezoid-circle-2** `circle, isosceles-trapezoid, diagonals, congruent`

> Draw a circle with center O. Draw one diameter from A to B. Now place two more points C and D on the same side of (and above) AB on the circle, so that D is above A and C is above B, making DC parallel to AB but shorter. Connect A to D, D to C, C to B, and B to A to form isosceles trapezoid ABCD. Draw both diagonals AC and DB. I want to see that the diagonals are congruent and that the base angles (angle DAB and angle CBA) are equal. Mark the equal diagonal lengths and the equal base angles.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `parallel(['D', 'C'], ['A', 'B'])`, `equal_lengths(['A', 'C'], ['D', 'B'])`, `angle_equal(['D', 'A', 'B'], ['C', 'B', 'A'])`, `equal_lengths(['A', 'D'], ['B', 'C'])`

**geo-m2-t1-l2-a1-rectangle-inscribed-circle-1** `circle, inscribed-quadrilateral, rectangle, diameter`

> Draw a circle with center O. Draw two diameters: one from A to C and another from B to D, where the two diameters are NOT perpendicular. Connect A to B, B to C, C to D, and D to A to form a quadrilateral ABCD inscribed in the circle. Label all four vertices and the center O. Mark the four right angles at A, B, C, and D (each inscribed angle intercepts a semicircle), and mark the two diagonals AC and BD as equal in length since they're both diameters.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, C)`, `point_on_circle(B, O, C)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_segment(O, A, C)`, `point_on_segment(O, B, D)`, `equal_lengths(['A', 'C'], ['B', 'D'])`, `right_angle(D, A, B)`, `right_angle(A, B, C)`

**geo-m2-t1-l2-a2-rhombus-concentric-circles-1** `concentric-circles, rhombus, perpendicular-diagonals`

> Draw two concentric circles (same center O, different radii). On the inner circle put points A and C at opposite ends of a diameter. On the outer circle put points B and D at opposite ends of a different diameter, but rotated so it's not the same direction as AC. Connect A to B, B to C, C to D, and D to A to form quadrilateral ABCD. Since all sides come from connecting equal-radius points on alternating circles, this should be a rhombus. Draw the diagonals AC and BD and mark where they intersect at O. Show that the diagonals are perpendicular and that O is the midpoint of each diagonal. Mark all four sides as equal.

Labels: O, A, B, C, D
Properties: `perpendicular(['A', 'C'], ['B', 'D'])`, `midpoint(O, A, C)`, `midpoint(O, B, D)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'A'])`, `right_angle(A, O, B)`

**geo-m2-t1-l2-a4-midsegment-quadrilateral-1** `quadrilateral, midsegment, midpoint, parallelogram`

> Draw a quadrilateral ABCD (a general one, not a special shape). Find and mark the midpoints of each side: call them E (midpoint of AB), F (midpoint of BC), G (midpoint of CD), and H (midpoint of DA). Connect E to F, F to G, G to H, and H to E to form the inner quadrilateral EFGH. I want to show this inner shape is always a parallelogram — mark EF parallel to HG and EH parallel to FG. Label all eight points.

Labels: A, B, C, D, E, F, G, H
Properties: `midpoint(E, A, B)`, `midpoint(F, B, C)`, `midpoint(G, C, D)`, `midpoint(H, D, A)`, `parallel(['E', 'F'], ['H', 'G'])`, `parallel(['E', 'H'], ['F', 'G'])`, `mark_present(midpoint, E)`, `mark_present(midpoint, F)`, `mark_present(midpoint, G)`, `mark_present(midpoint, H)`

**geo-m2-t1-l2-a4-trapezoid-midsegment-2** `trapezoid, midsegment, midpoint, parallel`

> Draw a trapezoid ABCD where AB is the bottom base (longer) and DC is the top base (shorter), and AB is parallel to DC. Find the midpoints of the two legs: call M the midpoint of AD and N the midpoint of BC. Draw the midsegment MN connecting these two midpoints. I want to show that MN is parallel to both bases AB and DC, and that MN's length equals half of (AB + DC). Please label all 6 points and mark M and N as midpoints.

Labels: A, B, C, D, M, N
Properties: `midpoint(M, A, D)`, `midpoint(N, B, C)`, `parallel(['A', 'B'], ['D', 'C'])`, `parallel(['M', 'N'], ['A', 'B'])`, `parallel(['M', 'N'], ['D', 'C'])`, `mark_present(midpoint, M)`, `mark_present(midpoint, N)`

**geo-m2-t1-l2-a5-inscribed-quadrilateral-opposite-angles-1** `circle, inscribed-quadrilateral, cyclic-quadrilateral, supplementary-angles`

> Draw a circle with center O and inscribe a quadrilateral ABCD in it — all four vertices A, B, C, D should be on the circle. Make it a general quadrilateral (not a rectangle). Label the four interior angles at each vertex. I want to show that opposite angles are supplementary: angle A + angle C = 180 degrees and angle B + angle D = 180 degrees. If you can, label angle A as 110 degrees and angle C as 70 degrees, and label angle B as 85 degrees and angle D as 95 degrees to show each pair adds to 180.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m2-t1-l3-a0-equilateral-triangle-circle-1** `circle, equilateral-triangle, inscribed-polygon, radius-chord`

> Draw a circle with center O and radius OA. Using the radius length as the chord length, mark point B on the circle so that AB equals the radius OA. Then mark C so BC also equals the radius. Connect A to B to C and back to A to form an equilateral triangle inscribed in the circle. Draw radii OA, OB, and OC. Label all points, mark all three sides of the triangle as equal, and label each central angle (AOB, BOC, COA) as 60 degrees.

Labels: O, A, B, C
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'A'])`, `equal_lengths(['O', 'A'], ['O', 'B'], ['O', 'C'])`, `equal_lengths(['A', 'B'], ['O', 'A'])`

**geo-m2-t1-l3-a2-inscribed-hexagon-circle-1** `circle, regular-hexagon, inscribed-polygon, congruent-chords`

> Draw a circle with center O. Starting at point A on the circle, use the radius length to mark off six equally spaced points around the circle: A, B, C, D, E, F. Connect them in order — A to B, B to C, C to D, D to E, E to F, and F back to A — to make a regular hexagon inscribed in the circle. Draw all six radii from O to each vertex. Mark all six sides of the hexagon as equal (each equals the radius), and label one interior angle of the hexagon as 120 degrees.

Labels: O, A, B, C, D, E, F
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_circle(E, O, A)`, `point_on_circle(F, O, A)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'E'], ['E', 'F'], ['F', 'A'])`, `equal_lengths(['A', 'B'], ['O', 'A'])`

**geo-m2-t1-l3-a3-inscribed-square-perpendicular-diameters-1** `circle, inscribed-square, perpendicular-diameters, pythagorean-theorem`

> Draw a circle with center O. Draw two perpendicular diameters: one from A to C (horizontal) and one from B to D (vertical), crossing at O at a right angle. Connect A to B, B to C, C to D, and D to A to form a square ABCD inscribed in the circle. Mark the right angle at O where the diameters cross, mark all four sides as equal, and draw a tick mark on each side. Label all four vertices and center O. Also mark a right angle at vertex A to show the inscribed angle intercepting a semicircle is 90 degrees.

Labels: O, A, B, C, D
Properties: `point_on_circle(A, O, C)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `perpendicular(['A', 'C'], ['B', 'D'])`, `right_angle(A, O, B)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'A'])`, `right_angle(D, A, B)`, `point_on_segment(O, A, C)`, `point_on_segment(O, B, D)`

**geo-m2-t1-l4-a2-exterior-angle-1** `triangle, exterior-angle, remote-interior-angles`

> Draw triangle ABC. Extend side BC beyond C to a point D, creating exterior angle ACD. I want to show that the exterior angle ACD equals the sum of the two remote interior angles: angle A and angle B. Mark angle ACD, angle CAB, and angle ABC with arc marks, and label all four points A, B, C, D. Show with labels or notes that angle ACD = angle CAB + angle ABC.

Labels: A, B, C, D
Properties: `collinear(B, C, D)`, `point_on_segment(C, B, D)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m2-t1-l4-a2-triangle-angle-sum-parallel-1** `triangle, angle-sum, parallel-lines, alternate-interior-angles`

> Draw triangle ABC. Then draw a line through vertex B that is parallel to side AC — label two points on this line as D and E so that D is to the left of B and E is to the right of B. I want to use this to show the triangle angle sum is 180 degrees: angle DBA equals angle BAC (alternate interior angles), angle EBC equals angle BCA (alternate interior angles), and angle DBA + angle ABC + angle EBC = 180 degrees because they form a straight line at B. Mark the equal angle pairs with matching arc marks.

Labels: A, B, C, D, E
Properties: `parallel(['D', 'E'], ['A', 'C'])`, `point_on_segment(B, D, E)`, `angle_equal(['D', 'B', 'A'], ['B', 'A', 'C'])`, `angle_equal(['E', 'B', 'C'], ['B', 'C', 'A'])`, `collinear(D, B, E)`

**geo-m2-t1-l4-a3-triangle-midsegment-1** `triangle, midsegment, midpoint, parallel`

> Draw triangle ABC where AB is the bottom and C is the top vertex. Find the midpoint of AC and call it M, and find the midpoint of BC and call it N. Draw segment MN — this is the midsegment. I want to show two things: (1) MN is parallel to AB, and (2) MN is half the length of AB. Mark M and N as midpoints with tick marks on their respective sides, draw arrows on MN and AB to show they're parallel, and label all five points A, B, C, M, N.

Labels: A, B, C, M, N
Properties: `midpoint(M, A, C)`, `midpoint(N, B, C)`, `parallel(['M', 'N'], ['A', 'B'])`, `mark_present(midpoint, M)`, `mark_present(midpoint, N)`

**geo-m2-t2-l1-a13-congruent-supplements-1** `supplementary-angles, congruent-supplements-theorem, two-column-proof`

> Draw two separate pairs of supplementary angles. For the first pair, label the angles as angle 1 and angle 2 sitting on a straight line. For the second pair, label them as angle 3 and angle 2 — same angle 2! — also on a straight line. Mark angle 1 and angle 3 with a single arc each to show they're congruent. This is to prove the congruent supplements theorem: if angle 1 and angle 3 are both supplementary to angle 2, then angle 1 equals angle 3.

Labels: 1, 2, 3
Properties: `angle_equal(['1', 'vertex1', '2'], ['3', 'vertex2', '2'])`, `angle_equal(['1', 'vertex1', 'ref1'], ['3', 'vertex2', 'ref2'])`

**geo-m2-t2-l1-a14-vertical-angle-theorem-proof-1** `vertical-angles, paragraph-proof, two-column-proof`

> Draw two lines intersecting at point O. Label four rays going out from O as OA, OB, OC, OD where A and C are on opposite sides (so AOC is a straight line) and B and D are on opposite sides (so BOD is a straight line). Label the four angles: angle AOB, angle BOC, angle COD, angle DOA. Put matching arc marks on the vertical angle pairs — single arcs on angle AOB and angle COD, and double arcs on angle BOC and angle DOA.

Labels: A, B, C, D, O
Properties: `collinear(A, O, C)`, `collinear(B, O, D)`, `angle_equal(['A', 'O', 'B'], ['C', 'O', 'D'])`, `angle_equal(['B', 'O', 'C'], ['D', 'O', 'A'])`

**geo-m2-t2-l1-a15-algebraic-angles-1** `vertical-angles, linear-pair, algebraic-expressions`

> Draw two lines intersecting at point O. Label four angles: the top angle is (3x + 10)°, the left angle is (5x - 20)°, the bottom angle is (3x + 10)°, and the right angle is (5x - 20)°. This setup shows vertical angles are equal and adjacent angles are a linear pair summing to 180°. I need to solve for x.

Labels: O
Properties: `angle_equal(['top', 'O', 'bottom'], ['left', 'O', 'right'])`

**geo-m2-t2-l1-gs-vertical-angles-2** `linear-pair, angle-addition-postulate, supplementary-angles`

> Draw two lines crossing at point O. Put rays going out in four directions and label the endpoints A, B, C, D so that A and C are on opposite rays and B and D are on opposite rays. I need to see that angle AOB and angle BOC are a linear pair sitting on line AC, and that angle AOB and angle COD are vertical angles.

Labels: A, B, C, D, O
Properties: `collinear(A, O, C)`, `collinear(B, O, D)`, `angle_equal(['A', 'O', 'B'], ['C', 'O', 'D'])`

**geo-m2-t2-l2-a21-corresponding-angles-algebraic-1** `corresponding-angles-theorem, parallel-lines, algebraic-expressions`

> Draw two parallel lines (mark them with arrows) cut by a transversal. At the top intersection point P, label one angle as (4x + 15)°. At the bottom intersection point Q, label the corresponding angle — in the same position relative to the intersection — as (7x - 18)°. I need to set those equal and solve for x to practice the corresponding angles theorem.

Labels: P, Q
Properties: `angle_equal(['ref1', 'P', 'ref2'], ['ref1', 'Q', 'ref2'])`, `parallel(['P', 'left'], ['Q', 'left'])`

**geo-m2-t2-l2-a22-same-side-interior-1** `same-side-interior-angles, supplementary-angles, flow-chart-proof`

> Draw two parallel lines cut by a transversal. Label the intersections as points E (top) and F (bottom). At E, label the interior angle on the right side as (2x + 40)°. At F, label the interior angle on the right side — it's on the same side as the first one, between the parallel lines — as (3x + 25)°. These two same-side interior angles should add up to 180°. Mark the parallel lines with tick arrows.

Labels: E, F
Properties: `parallel(['E', 'left_E'], ['F', 'left_F'])`

**geo-m2-t2-l2-a23-alternate-interior-angles-1** `alternate-interior-angles, two-column-proof, flow-chart-proof`

> Draw two parallel lines cut by a transversal, with intersections at points G (top line) and H (bottom line). I want to see the two alternate interior angles highlighted: the angle below line-G on the left of the transversal, and the angle above line-H on the right of the transversal. Label them angle 3 and angle 6. Put matching arc marks on them to show they're equal.

Labels: G, H, 3, 6
Properties: `angle_equal(['ref1', 'G', 'ref2'], ['ref3', 'H', 'ref4'])`, `parallel(['G', 'left'], ['H', 'left'])`

**geo-m2-t2-l2-a24-converse-alternate-interior-1** `alternate-interior-angles-converse, parallel-lines, two-column-proof`

> Draw two lines (not yet marked as parallel) cut by a transversal, with intersections at points J and K. Label the alternate interior angles: angle 4 at J (below J, on the left of transversal) and angle 5 at K (above K, on the right of transversal). Mark both with a single arc to show they're given as congruent. I want to prove those two lines must be parallel — so leave the lines unlabeled as parallel for now, and I'll prove it.

Labels: J, K, 4, 5
Properties: `angle_equal(['ref1', 'J', 'ref2'], ['ref3', 'K', 'ref4'])`

**geo-m2-t2-l2-a25-perpendicular-parallel-1** `perpendicular-lines, parallel-lines, perpendicular-parallel-theorem`

> Draw three horizontal lines — label the top one l, the middle one m, and the bottom one n. Now draw a vertical transversal line t crossing all three. Put right angle marks at the intersections of t with l and t with m to show those two lines are perpendicular to t. I want to see that this means l is parallel to m. Mark l and m as parallel with arrows.

Labels: l, m, n, t
Properties: `perpendicular(['l_left', 'l_right'], ['t_top', 't_bottom'])`, `perpendicular(['m_left', 'm_right'], ['t_top', 't_bottom'])`, `parallel(['l_left', 'l_right'], ['m_left', 'm_right'])`

**geo-m2-t2-l2-tt-eight-angles-labeled-1** `parallel-lines, transversal, all-angle-pairs`

> Draw two parallel lines p and q cut by transversal r. Label all eight angles: angles 1, 2, 3, 4 at the upper intersection (point M) and angles 5, 6, 7, 8 at the lower intersection (point N), numbered clockwise from upper-left at each. Mark the parallel lines with double arrows. I want to reference all eight angles when I practice identifying corresponding, alternate interior, alternate exterior, and same-side interior pairs.

Labels: p, q, r, M, N, 1, 2, 3, 4, 5, 6, 7, 8
Properties: `parallel(['M', 'p_end'], ['N', 'q_end'])`, `angle_equal(['ref1', 'M', 'ref2'], ['ref5', 'N', 'ref6'])`

**geo-m2-t2-l3-a31-exterior-angle-theorem-1** `exterior-angle-theorem, remote-interior-angles, triangle`

> Draw triangle PQR. Extend side QR past R to a point S so you can see the exterior angle PRS. Label angle PRS as the exterior angle. Label angle QPR and angle PQR as the two remote interior angles. Mark with arcs that angle PRS equals angle QPR plus angle PQR. I want to use this to show the exterior angle theorem.

Labels: P, Q, R, S
Properties: `collinear(Q, R, S)`, `angle_equal(['P', 'R', 'S'], ['Q', 'P', 'R'])`

**geo-m2-t2-l3-a31-triangle-sum-auxiliary-1** `triangle-sum-theorem, auxiliary-line, alternate-interior-angles, paragraph-proof`

> Draw triangle ABC with A at the top, B at the bottom-left, C at the bottom-right. Draw an auxiliary line DE through vertex A that is parallel to side BC. Mark the parallel lines with arrows. Label angle DAB as equal to angle ABC (alternate interior angles — put matching single-arc marks), and label angle EAC as equal to angle BCA (alternate interior angles — put matching double-arc marks). Show that angle DAB, angle BAC, and angle EAC together form the straight angle at A along line DE.

Labels: A, B, C, D, E
Properties: `parallel(['D', 'E'], ['B', 'C'])`, `point_on_line(A, D, E)`, `angle_equal(['D', 'A', 'B'], ['A', 'B', 'C'])`, `angle_equal(['E', 'A', 'C'], ['B', 'C', 'A'])`

**geo-m2-t2-l3-a32-polygon-diagonals-1** `polygon, diagonals, interior-angle-sum`

> Draw three polygons side by side: a quadrilateral ABCD, a pentagon ABCDE, and a hexagon ABCDEF. In each one, draw all diagonals from vertex A only — this divides each polygon into triangles. Label the triangles in each polygon. Under each polygon write the number of triangles formed and multiply by 180 degrees to show the interior angle sum formula 180(n-2).

Labels: A, B, C, D, E, F
Properties: `point_on_segment(A, A, C)`, `point_on_segment(A, A, C)`, `point_on_segment(A, A, D)`

**geo-m2-t2-l3-a33-exterior-angles-polygon-1** `exterior-angles, polygon, 360-degrees`

> Draw a convex pentagon ABCDE. At each vertex, extend one side to show the exterior angle. Label the exterior angles as angle 1 at A, angle 2 at B, angle 3 at C, angle 4 at D, and angle 5 at E. Put a small arc at each exterior angle. I want to see that all five exterior angles together add up to 360 degrees.

Labels: A, B, C, D, E, 1, 2, 3, 4, 5
Properties: `mark_present(arc, A)`, `mark_present(arc, B)`, `mark_present(arc, C)`, `mark_present(arc, D)`, `mark_present(arc, E)`

**geo-m2-t2-l3-gs-triangle-rotation-1** `triangle-sum-theorem, rotation, translation, straight-angle`

> Draw triangle ABC. Then show a translated and rotated copy so that angle A, angle B, and angle C all end up touching each other and lying flat along a straight horizontal line. Label the three adjacent angles as angle A, angle B, angle C in a row along the line to show they form a 180-degree straight angle. This illustrates why the interior angles of a triangle sum to 180 degrees.

Labels: A, B, C
Properties: `collinear(A_ray, B_vertex, C_ray)`

**geo-m2-t2-l4-a41-perpendicular-bisector-theorem-1** `perpendicular-bisector, CPCTC, congruent-triangles`

> Draw a line segment AB with midpoint M. Draw the perpendicular bisector through M — call it line l. Place a point P somewhere on line l above the segment. Draw segments PA and PB. Put a right angle mark where line l crosses AB at M. Put single tick marks on AM and MB to show they're equal. Put double tick marks on PA and PB to show they're equal. This diagram shows the perpendicular bisector theorem.

Labels: A, B, M, P, l
Properties: `midpoint(M, A, B)`, `perpendicular(['P', 'M'], ['A', 'B'])`, `equal_lengths(['A', 'M'], ['M', 'B'])`, `equal_lengths(['P', 'A'], ['P', 'B'])`, `right_angle(A, M, P)`, `point_on_line(P, M, l_end)`

**geo-m2-t2-l4-a42-isosceles-base-angles-1** `isosceles-triangle, base-angles-theorem, auxiliary-line`

> Draw an isosceles triangle ABC where AB equals AC (mark them with tick marks). Draw the angle bisector from vertex A down to point D on BC. Label the two base angles at B and C with matching arcs to show they're congruent. Mark the right angle at D or the equal segments BD and DC if using the median. This is for proving the isosceles base angles theorem using an auxiliary line.

Labels: A, B, C, D
Properties: `equal_lengths(['A', 'B'], ['A', 'C'])`, `point_on_segment(D, B, C)`, `angle_bisector(D, A, B, C)`, `angle_equal(['A', 'B', 'C'], ['A', 'C', 'B'])`

**geo-m2-t2-l4-a43-30-60-90-triangle-1** `special-right-triangles, 30-60-90, equilateral-triangle, perpendicular-bisector`

> Draw an equilateral triangle with vertices X, Y, Z where all sides are length 2s. Drop a perpendicular bisector from X to the midpoint M of YZ. This splits it into two 30-60-90 triangles. Label the angles: 60° at X (in each half), 90° at M, and 30° at Y and Z. Label the sides: YM = MZ = s (with tick marks), XY = XZ = 2s, and XM = s√3. Put a right angle mark at M.

Labels: X, Y, Z, M
Properties: `midpoint(M, Y, Z)`, `perpendicular(['X', 'M'], ['Y', 'Z'])`, `right_angle(X, M, Y)`, `equal_lengths(['Y', 'M'], ['M', 'Z'])`, `equal_lengths(['X', 'Y'], ['X', 'Z'])`

**geo-m2-t2-l4-a43-45-45-90-triangle-1** `special-right-triangles, 45-45-90, isosceles-right-triangle`

> Draw an isosceles right triangle PQR where the right angle is at Q, and legs PQ and QR both have length a. Label angle P = 45° and angle R = 45°. Label the hypotenuse PR as a√2. Put a right angle mark at Q and tick marks on both legs to show they're equal. This is the 45-45-90 triangle theorem diagram.

Labels: P, Q, R
Properties: `right_angle(P, Q, R)`, `equal_lengths(['P', 'Q'], ['Q', 'R'])`, `angle_equal(['Q', 'P', 'R'], ['P', 'R', 'Q'])`

**geo-m2-t2-l4-tt-square-diagonal-1** `45-45-90, square, diagonal`

> Draw a square ABCD with side length 8 units. Draw diagonal AC. Mark the right angle at each corner with a small square. Label each side as 8 units. Label the diagonal AC as 8√2. Mark the 45° angles that the diagonal makes at vertices A and C.

Labels: A, B, C, D
Properties: `right_angle(D, A, B)`, `right_angle(A, B, C)`, `right_angle(B, C, D)`, `right_angle(C, D, A)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'A'])`

**geo-m2-t2-l5-a51-indirect-proof-triangle-1** `indirect-proof, proof-by-contradiction, triangle`

> Draw triangle ABC with a segment CD drawn from vertex C to a point D on AB. Label the given information: AC = 6, BC = 4, AD = 3, DB = 3 — so D is the midpoint of AB. Mark the sides with tick marks. I want to show by contradiction that segment CD does NOT bisect angle ACB, so mark angle ACD and angle DCB as if someone assumed they were equal, and then we show that leads to a contradiction.

Labels: A, B, C, D
Properties: `midpoint(D, A, B)`, `point_on_segment(D, A, B)`, `label_present(AC=6)`, `label_present(BC=4)`

**geo-m2-t2-l5-a52-hinge-theorem-1** `hinge-theorem, two-triangles, indirect-proof`

> Draw two separate triangles side by side. Triangle 1 is ABC and Triangle 2 is DEF. Mark AB = DE and AC = DF with single and double tick marks. In triangle ABC, label the included angle at A as 80°. In triangle DEF, label the included angle at D as 50°. Then label BC and EF as the third sides that we're comparing — put a label showing BC > EF because the larger included angle gives the longer opposite side. This is the hinge theorem.

Labels: A, B, C, D, E, F
Properties: `equal_lengths(['A', 'B'], ['D', 'E'])`, `equal_lengths(['A', 'C'], ['D', 'F'])`, `label_present(80°)`, `label_present(50°)`

**geo-m2-t2-l6-a61-inscribed-angle-isosceles-proof-1** `inscribed-angle-theorem, isosceles-triangle, radii, two-column-proof`

> Draw a circle with center O. Place point A on the circle and draw two radii OB and OC to two other points B and C on the circle. Draw chord BC. Now also draw chord AB so that angle BAC is an inscribed angle intercepting arc BC. Draw the radius OA so triangle OAB is isosceles (OA = OB, mark with tick marks) and triangle OAC is isosceles (OA = OC, mark with different tick marks). I'm using this to prove case 1 of the inscribed angle theorem where angle BAC = half of central angle BOC.

Labels: A, B, C, O
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `equal_lengths(['O', 'A'], ['O', 'B'])`, `equal_lengths(['O', 'A'], ['O', 'C'])`

**geo-m2-t2-l6-a61-inscribed-angle-three-cases-1** `inscribed-angle-theorem, circle, three-cases`

> Draw three separate circles, each with center O. In circle 1, draw inscribed angle BAC where the center O lies ON side AC of the angle. In circle 2, draw inscribed angle BAC where O is in the INTERIOR of the angle. In circle 3, draw inscribed angle BAC where O is in the EXTERIOR of the angle. Label all three with points A, B, C, O and draw the intercepted arc BC in each. Label the central angle BOC in each circle.

Labels: A, B, C, O
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`

**geo-m2-t2-l6-a62-inscribed-quadrilateral-1** `inscribed-quadrilateral, opposite-angles, supplementary`

> Draw a circle and inscribe quadrilateral QUAD inside it — so all four vertices Q, U, A, D lie on the circle. Label angle Q and angle A as one pair of opposite angles, and angle U and angle D as the other pair. Mark angle Q and angle A each with a single arc to show they're supplementary (add to 180°). Mark angle U and angle D with double arcs to show they're also supplementary. This is the inscribed quadrilateral opposite angles theorem.

Labels: Q, U, A, D
Properties: `point_on_circle(Q, O, U)`, `point_on_circle(U, O, Q)`, `point_on_circle(A, O, Q)`, `point_on_circle(D, O, Q)`

**geo-m2-t2-l6-a62-inscribed-right-triangle-1** `inscribed-right-triangle, diameter, semicircle, two-column-proof`

> Draw a circle with center O and diameter AC (so A and C are endpoints of a diameter on opposite sides). Place a point B on the circle above the diameter. Draw triangle ABC inscribed in the circle. Mark the right angle at B with a small square. Label the arc AC as a semicircle = 180°. This diagram shows the inscribed right triangle-diameter theorem: if one side of an inscribed triangle is a diameter, the inscribed angle opposite it is 90°.

Labels: A, B, C, O
Properties: `point_on_circle(A, O, C)`, `point_on_circle(C, O, A)`, `point_on_circle(B, O, A)`, `collinear(A, O, C)`, `right_angle(A, B, C)`

**geo-m2-t2-l6-a63-interior-angles-circle-1** `interior-angles-circle, intersecting-chords, arc-measures`

> Draw a circle with two chords that intersect inside the circle at point P. Label the four endpoints of the chords as A, B, C, D so chord AB and chord CD cross at P. Label arc AC as 80° and arc BD as 60°. Put a label on angle APC showing it equals (80° + 60°)/2 = 70°. This is the interior angles of a circle theorem.

Labels: A, B, C, D, P
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_segment(P, A, B)`, `point_on_segment(P, C, D)`

**geo-m2-t2-l6-a65-tangent-radius-perpendicular-1** `tangent-to-circle, perpendicular, radius, proof-by-contradiction`

> Draw a circle with center O. Mark a point T on the circle. Draw the radius OT. Draw a tangent line l that touches the circle at exactly point T. Put a right angle mark where OT meets line l at T. Also draw the line from O to an external point E on line l, and label the right triangle OTE where OT is the radius, TE is the tangent distance, and OE is the line from center to external point. This illustrates the tangent to a circle theorem.

Labels: O, T, E, l
Properties: `point_on_circle(T, O, T)`, `perpendicular(['O', 'T'], ['E', 'T'])`, `right_angle(O, T, E)`, `tangent(['E', 'T'], O, T)`

**geo-m2-t3-l1-a1-hl-proof-triangles-1** `right-triangle, HL, congruence, proof, Pythagorean-theorem`

> I need two right triangles side by side to help me follow a proof of the Hypotenuse-Leg theorem. Draw triangle ABC on the left with the right angle at C, and triangle DEF on the right with the right angle at F. Make the hypotenuses AB and DE the same length, and make legs AC and DF the same length. Mark the right angles at C and F with squares, mark the equal hypotenuses with one tick mark each, and mark the equal legs AC and DF with double tick marks. Label all six vertices.

Labels: A, B, C, D, E, F
Properties: `right_angle(A, C, B)`, `right_angle(D, F, E)`, `mark_present(right_angle, C)`, `mark_present(right_angle, F)`, `equal_lengths(['A', 'B'], ['D', 'E'])`, `equal_lengths(['A', 'C'], ['D', 'F'])`

**geo-m2-t3-l1-a2-ll-congruence-perpendicular-midpoint-1** `right-triangle, LL, LA, perpendicular, midpoint, congruence`

> Draw two right triangles that share a common vertex. Make segment AB horizontal, and let M be the midpoint of AB. Draw a segment MC that goes straight up from M so that MC is perpendicular to AB — this creates two right triangles, triangle AMC on the left and triangle BMC on the right. Mark the right angles at M in both triangles with squares, mark M as the midpoint of AB with tick marks on AM and MB, and label points A, M, B, and C. I'm trying to use the Leg-Leg theorem to show these two right triangles are congruent.

Labels: A, M, B, C
Properties: `midpoint(M, A, B)`, `perpendicular(['C', 'M'], ['A', 'B'])`, `right_angle(A, M, C)`, `right_angle(B, M, C)`, `equal_lengths(['A', 'M'], ['M', 'B'])`, `perpendicular(['C', 'M'], ['A', 'B'])`

**geo-m2-t3-l2-a1-tangent-circles-external-tangent-1** `circle, tangent, tangent-circles, external-tangent`

> Draw two circles that are tangent to each other externally — they touch at exactly one point, call it T. Label the center of the smaller circle as O1 and the center of the larger circle as O2. Draw a common external tangent line that touches the smaller circle at point A and the larger circle at point B. Label all four points O1, O2, A, B, and T. I need this to practice problems about tangent circles and tangent segments.

Labels: O1, O2, A, B, T
Properties: `tangent(['A', 'B'], O1, A)`, `tangent(['A', 'B'], O2, B)`, `point_on_circle(T, O1, T)`, `point_on_circle(T, O2, T)`, `label_present(T)`

**geo-m2-t3-l2-a1-tangent-segment-theorem-1** `circle, tangent, tangent-segment, HL, congruence, exterior-point`

> Draw a circle with center O. Then pick an exterior point P outside the circle. Draw two tangent lines from P to the circle — one touching the circle at point A and one touching at point B. Draw the radii OA and OB to the tangent points, and also draw the line segment OP. I need to see that PA and PB are the two tangent segments, and that OA is perpendicular to PA and OB is perpendicular to PB. Mark those right angles with squares. Label all points O, P, A, and B, and mark PA and PB with tick marks to show they're equal (that's what I'm trying to prove).

Labels: O, P, A, B
Properties: `right_angle(O, A, P)`, `right_angle(O, B, P)`, `mark_present(right_angle, A)`, `mark_present(right_angle, B)`, `equal_lengths(['P', 'A'], ['P', 'B'])`, `point_on_circle(A, O, A)`, `point_on_circle(B, O, B)`

**geo-m2-t3-l2-a2-diameter-chord-theorem-1** `circle, chord, diameter, perpendicular-bisector, proof`

> Draw a circle with center O. Draw a chord AB that is NOT a diameter — so it doesn't pass through O. Now draw the diameter that is perpendicular to chord AB and label the point where the diameter crosses the chord as M. Show that M is the midpoint of AB by marking AM and MB with tick marks. Mark the right angle where the diameter meets AB with a square. Label O, A, B, and M. This is for the diameter-chord theorem that says a diameter perpendicular to a chord bisects it.

Labels: O, A, B, M
Properties: `midpoint(M, A, B)`, `perpendicular(['O', 'M'], ['A', 'B'])`, `right_angle(A, M, O)`, `mark_present(right_angle, M)`, `equal_lengths(['A', 'M'], ['M', 'B'])`, `point_on_segment(M, A, B)`

**geo-m2-t3-l2-a2-equidistant-chord-theorem-1** `circle, chord, equidistant, congruent-chords, proof`

> Draw a circle with center O and two congruent chords inside it — call them chord AB and chord CD. Draw perpendicular segments from the center O to each chord: let E be the foot of the perpendicular from O to chord AB, and let F be the foot of the perpendicular from O to chord CD. Mark the right angles at E and F with squares. Mark chord AB and chord CD with single tick marks to show they're equal, and mark OE and OF with double tick marks to show those distances from the center are equal. Label all points O, A, B, C, D, E, and F.

Labels: O, A, B, C, D, E, F
Properties: `right_angle(O, E, A)`, `right_angle(O, F, C)`, `mark_present(right_angle, E)`, `mark_present(right_angle, F)`, `equal_lengths(['A', 'B'], ['C', 'D'])`, `equal_lengths(['O', 'E'], ['O', 'F'])`, `point_on_segment(E, A, B)`, `point_on_segment(F, C, D)`

**geo-m2-t3-l2-a3-congruent-chord-arc-theorem-1** `circle, chord, arc, central-angle, congruent, SSS, proof`

> Draw a circle with center O and two congruent chords inside it. Call the endpoints of the first chord A and B, and the endpoints of the second chord C and D, where all four points are on the circle. Draw all four radii: OA, OB, OC, and OD. This creates two triangles — triangle OAB and triangle OCD. Mark chord AB and chord CD with tick marks to show they're congruent. Mark the four radii OA, OB, OC, OD with the same tick mark to show they're all equal (radii of the same circle). Label the central angles — call angle AOB and angle COD — to show they're equal. Label all five points O, A, B, C, and D.

Labels: O, A, B, C, D
Properties: `equal_lengths(['A', 'B'], ['C', 'D'])`, `equal_lengths(['O', 'A'], ['O', 'C'])`, `equal_lengths(['O', 'B'], ['O', 'D'])`, `angle_equal(['A', 'O', 'B'], ['C', 'O', 'D'])`, `point_on_circle(A, O, A)`, `point_on_circle(B, O, B)`, `point_on_circle(C, O, C)`, `point_on_circle(D, O, D)`

**geo-m2-t3-l2-gs-broken-plate-chord-1** `circle, chord, perpendicular-bisector, diameter, real-world`

> Draw a circle that looks like a broken plate — only show roughly the top two-thirds of the circle, like the bottom part broke off. Draw two chords inside the fragment, call their endpoints A, B for the first chord and C, D for the second chord. Then draw the perpendicular bisector of chord AB and the perpendicular bisector of chord CD, and mark the point where these two perpendicular bisectors cross as point P. P should be right at the center of the original circle. Label all points A, B, C, D, and P, and mark the right angles where the bisectors meet the chords.

Labels: A, B, C, D, P
Properties: `perpendicular(['A', 'B'], ['P', 'A'])`, `perpendicular(['C', 'D'], ['P', 'C'])`, `label_present(P)`, `midpoint(P, A, B)`

**geo-m2-t3-l3-a1-parallelogram-diagonals-1** `parallelogram, diagonals, midpoint, bisect, congruence, proof`

> Draw parallelogram PARG where P is top-left, A is top-right, R is bottom-right, and G is bottom-left. Draw both diagonals PR and AG, and label the point where they cross as M. Mark PM and MR with tick marks to show they're equal, and mark AM and MG with double tick marks to show they're equal — this is to illustrate that the diagonals bisect each other. Also mark both pairs of opposite sides as parallel using arrows: PA parallel to GR, and PG parallel to AR. Mark opposite sides with matching tick marks to show PA equals GR and PG equals AR. Label all five points P, A, R, G, and M.

Labels: P, A, R, G, M
Properties: `midpoint(M, P, R)`, `midpoint(M, A, G)`, `parallel(['P', 'A'], ['G', 'R'])`, `parallel(['P', 'G'], ['A', 'R'])`, `equal_lengths(['P', 'A'], ['G', 'R'])`, `equal_lengths(['P', 'G'], ['A', 'R'])`, `equal_lengths(['P', 'M'], ['M', 'R'])`, `equal_lengths(['A', 'M'], ['M', 'G'])`, `point_on_segment(M, P, R)`, `point_on_segment(M, A, G)`

**geo-m2-t3-l3-a1-rhombus-perpendicular-diagonals-1** `rhombus, diagonals, perpendicular, angle-bisector, proof`

> Draw rhombus RHOM where the vertices go in order: R at the top, H on the right, O at the bottom, and M on the left. Draw both diagonals RO and HM, and label their intersection point as X. Mark all four sides RH, HO, OM, and MR with tick marks to show they're all equal. Mark the right angle at X to show the diagonals are perpendicular. Also show that diagonal RO bisects angle R and angle O by marking those split angles with matching arcs. Label all five points R, H, O, M, and X.

Labels: R, H, O, M, X
Properties: `equal_lengths(['R', 'H'], ['H', 'O'], ['O', 'M'], ['M', 'R'])`, `perpendicular(['R', 'O'], ['H', 'M'])`, `right_angle(R, X, H)`, `mark_present(right_angle, X)`, `angle_bisector(X, R, M, H)`, `angle_bisector(X, H, R, O)`, `point_on_segment(X, R, O)`, `point_on_segment(X, H, M)`

**geo-m2-t3-l3-a2-rectangle-congruent-diagonals-1** `rectangle, diagonals, congruent, SAS, proof`

> Draw rectangle RECT with R at bottom-left, E at bottom-right, C at top-right, and T at top-left. Mark all four corners with right angle squares. Draw both diagonals RC and TE, and mark them with tick marks to show they're equal in length. Also mark the opposite sides as parallel with arrows: RE parallel to TC, and RT parallel to EC. Mark RE and TC with one set of tick marks showing they're equal, and mark RT and EC with another set. Label all four vertices R, E, C, and T. This is for proving diagonals of a rectangle are congruent.

Labels: R, E, C, T
Properties: `right_angle(T, R, E)`, `right_angle(R, E, C)`, `right_angle(E, C, T)`, `right_angle(C, T, R)`, `mark_present(right_angle, R)`, `mark_present(right_angle, E)`, `mark_present(right_angle, C)`, `mark_present(right_angle, T)`, `equal_lengths(['R', 'C'], ['T', 'E'])`, `parallel(['R', 'E'], ['T', 'C'])`, `parallel(['R', 'T'], ['E', 'C'])`

**geo-m2-t3-l3-a3-isosceles-trapezoid-base-angles-1** `trapezoid, isosceles, base-angles, auxiliary-line, congruent, proof`

> Draw isosceles trapezoid TRAP where T is top-left, R is top-right, A is bottom-right, and P is bottom-left. Make TP the top base and AR the bottom base — mark TP and AR as parallel with arrows. Make the legs TA and PR equal in length and mark them with tick marks. Draw the two diagonals TA... wait, let me redo this: draw the diagonals TR and PA and mark them with double tick marks to show they're congruent. Also mark the base angles at A and P with matching arcs to show angle P equals angle A (the base angles are congruent). Now draw an auxiliary line from T that is parallel to PR and hits PA at a new point X. Label all points T, R, A, P, and X. Mark the right angles or matching angles created by the auxiliary line.

Labels: T, R, A, P, X
Properties: `parallel(['T', 'P'], ['A', 'R'])`, `equal_lengths(['T', 'A'], ['P', 'R'])`, `equal_lengths(['T', 'R'], ['P', 'A'])`, `angle_equal(['T', 'P', 'A'], ['R', 'A', 'P'])`, `parallel(['T', 'X'], ['P', 'R'])`, `point_on_segment(X, P, A)`

**geo-m2-t3-l3-a4-proving-parallelogram-from-sides-1** `parallelogram, proof, congruent-opposite-sides, diagonal, alternate-interior-angles`

> Draw quadrilateral ABCD where A is top-left, B is top-right, C is bottom-right, and D is bottom-left. Draw diagonal AC to split it into two triangles. Mark side AB and side DC with single tick marks to show they're equal, and mark side AD and side BC with double tick marks to show they're equal. I want to prove this quadrilateral is a parallelogram because its opposite sides are congruent. Label alternate interior angles formed by the diagonal: mark angle BAC equal to angle DCA with matching arcs, and mark angle BCA equal to angle DAC with matching arcs. Label all four vertices A, B, C, and D.

Labels: A, B, C, D
Properties: `equal_lengths(['A', 'B'], ['D', 'C'])`, `equal_lengths(['A', 'D'], ['B', 'C'])`, `point_on_segment(A, A, C)`, `angle_equal(['B', 'A', 'C'], ['D', 'C', 'A'])`, `angle_equal(['B', 'C', 'A'], ['D', 'A', 'C'])`, `parallel(['A', 'B'], ['D', 'C'])`, `parallel(['A', 'D'], ['B', 'C'])`

**geo-m2-t3-l3-a4-proving-rhombus-from-diagonals-1** `rhombus, diagonals, angle-bisector, proof, perpendicular`

> Draw quadrilateral RHOM with R at top, H at right, O at bottom, and M at left. Draw both diagonals RO and HM, and label their intersection as X. To show this is a rhombus, mark that the diagonals bisect the vertex angles: show angle MRX equals angle HRX with matching arcs at R, and show angle MOR equal to angle HOX with arcs at O. Also mark the diagonals as perpendicular at X with a right angle square. Mark all four sides equal with tick marks to show the conclusion that all sides are equal. Label R, H, O, M, and X.

Labels: R, H, O, M, X
Properties: `angle_bisector(X, R, M, H)`, `angle_bisector(X, O, H, M)`, `perpendicular(['R', 'O'], ['H', 'M'])`, `mark_present(right_angle, X)`, `equal_lengths(['R', 'H'], ['H', 'O'], ['O', 'M'], ['M', 'R'])`, `point_on_segment(X, R, O)`, `point_on_segment(X, H, M)`

**geo-m3-t1-l1-act12-dilation-center-rays-1** `dilation, center-of-dilation, similar-figures, scale-factor`

> I need a diagram showing a triangle PQR and its dilated image P'Q'R' where the center of dilation is a point C that is NOT one of the triangle's vertices — maybe put C to the left of the triangle. Draw rays from C through P to P', from C through Q to Q', and from C through R to R'. The image should be bigger than the original (scale factor greater than 1). Label everything including the center C, and mark that the corresponding angles of PQR and P'Q'R' are congruent.

Labels: P, Q, R, P', Q', R', C
Properties: `collinear(C, P, P')`, `collinear(C, Q, Q')`, `collinear(C, R, R')`, `angle_equal(['Q', 'P', 'R'], ["Q'", "P'", "R'"])`, `angle_equal(['P', 'Q', 'R'], ["P'", "Q'", "R'"])`, `angle_equal(['P', 'R', 'Q'], ["P'", "R'", "Q'"])`, `label_present(C)`

**geo-m3-t1-l1-act14-similar-triangles-corresponding-parts-1** `similar-triangles, corresponding-parts, proportional-sides`

> Draw two similar triangles, triangle ABC and triangle DEF, where angle A corresponds to angle D, angle B corresponds to angle E, and angle C corresponds to angle F. Make triangle DEF larger than triangle ABC. Label all six vertices. Mark the equal angle pairs with matching tick marks (single arc at A and D, double arc at B and E, triple arc at C and F). Also label the sides: AB = 3, BC = 4, AC = 5, and the corresponding sides of DEF should be DE = 6, EF = 8, DF = 10 to show the scale factor of 2.

Labels: A, B, C, D, E, F
Properties: `angle_equal(['B', 'A', 'C'], ['E', 'D', 'F'])`, `angle_equal(['A', 'B', 'C'], ['D', 'E', 'F'])`, `angle_equal(['A', 'C', 'B'], ['D', 'F', 'E'])`, `mark_present(angle_single, A)`, `mark_present(angle_single, D)`, `mark_present(angle_double, B)`, `mark_present(angle_double, E)`

**geo-m3-t1-l1-gs-dilation-origin-1** `dilation, coordinate-plane, scale-factor, similarity`

> Can you draw triangle ABC on a coordinate plane where A is at (1, 2), B is at (3, 1), and C is at (2, 4)? Then show the dilation of triangle ABC from the origin with a scale factor of 2, labeling the image vertices A', B', and C'. Draw rays from the origin through each pair of corresponding vertices (like from O through A to A') so I can see how the dilation works.

Labels: A, B, C, A', B', C', O
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(A')`, `label_present(B')`, `label_present(C')`, `collinear(O, A, A')`, `collinear(O, B, B')`, `collinear(O, C, C')`, `equal_lengths(['O', 'A'], ['A', "A'"])`, `equal_lengths(['O', 'B'], ['B', "B'"])`, `equal_lengths(['O', 'C'], ['C', "C'"])`

**geo-m3-t1-l2-act21-aa-similarity-vertical-angles-1** `AA-similarity, vertical-angles, right-angles, similar-triangles`

> Can you draw two triangles that share a common vertex in the middle where two lines cross, creating vertical angles? Label the crossing point as E, and label the four outer vertices A, B, C, D so that triangle AEB and triangle CED are formed. Mark the vertical angles at E as equal. Also mark angle A and angle C as equal (both 40 degrees), and mark angle B and angle D as equal (both 70 degrees). This should show the AA similarity theorem using vertical angles.

Labels: A, B, C, D, E
Properties: `angle_equal(['A', 'E', 'B'], ['C', 'E', 'D'])`, `angle_equal(['B', 'A', 'E'], ['D', 'C', 'E'])`, `angle_equal(['A', 'B', 'E'], ['C', 'D', 'E'])`, `collinear(A, E, C)`, `collinear(B, E, D)`, `label_present(E)`

**geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1** `SSS-similarity, proportional-sides, similar-triangles`

> Draw two triangles side by side to show the SSS similarity theorem. Label the first triangle ABC with side lengths AB = 4, BC = 6, and AC = 5. Label the second triangle DEF with side lengths DE = 8, EF = 12, and DF = 10. These are similar because every pair of corresponding sides has the same ratio of 2. Mark the corresponding sides with matching tick marks: one tick on AB and DE, two ticks on BC and EF, three ticks on AC and DF.

Labels: A, B, C, D, E, F
Properties: `mark_present(tick_single, AB)`, `mark_present(tick_single, DE)`, `mark_present(tick_double, BC)`, `mark_present(tick_double, EF)`, `mark_present(tick_triple, AC)`, `mark_present(tick_triple, DF)`, `label_present(A)`, `label_present(D)`

**geo-m3-t1-l2-act23-sas-similarity-included-angle-1** `SAS-similarity, included-angle, proportional-sides`

> I need a diagram for the SAS similarity theorem. Draw triangle ABC where AB = 4, AC = 6, and angle A = 50 degrees. Then draw triangle DEF where DE = 8, DF = 12, and angle D = 50 degrees. The sides around angle A are proportional to the sides around angle D (ratio of 2), and the included angles are equal. Mark angle A and angle D with the same arc symbol to show they're congruent, and put one tick mark on AB and DE, and two tick marks on AC and DF.

Labels: A, B, C, D, E, F
Properties: `angle_equal(['B', 'A', 'C'], ['E', 'D', 'F'])`, `mark_present(angle_single, A)`, `mark_present(angle_single, D)`, `mark_present(tick_single, AB)`, `mark_present(tick_single, DE)`, `mark_present(tick_double, AC)`, `mark_present(tick_double, DF)`

**geo-m3-t1-l3-act34-triangle-proportionality-theorem-1** `triangle-proportionality, parallel-lines, proof`

> Draw triangle ABC with a line segment DE inside the triangle where D is on side AB and E is on side AC. Make DE parallel to side BC. Label the segments: AD = 3, DB = 6, AE = 2, EC = 4. Draw tick marks showing DE is parallel to BC (arrows on DE and BC). I want to see that AD/DB = AE/EC which is the Triangle Proportionality Theorem.

Labels: A, B, C, D, E
Properties: `parallel(['D', 'E'], ['B', 'C'])`, `point_on_segment(D, A, B)`, `point_on_segment(E, A, C)`, `label_present(D)`, `label_present(E)`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m3-t1-l3-act35-proportional-segments-three-parallel-lines-1** `proportional-segments, parallel-lines, transversals, proof`

> Draw three horizontal parallel lines and label them l1 (top), l2 (middle), and l3 (bottom). Then draw two transversals crossing all three lines. Label the points where the first transversal crosses the lines as A (on l1), B (on l2), and C (on l3). Label where the second transversal crosses as D (on l1), E (on l2), and F (on l3). Draw an auxiliary diagonal segment from A to F so you can see the two triangles formed inside. Show that AB/BC = DE/EF.

Labels: A, B, C, D, E, F
Properties: `parallel(['A', 'D'], ['B', 'E'])`, `parallel(['B', 'E'], ['C', 'F'])`, `collinear(A, B, C)`, `collinear(D, E, F)`, `point_on_segment(B, A, C)`, `point_on_segment(E, D, F)`, `label_present(A)`, `label_present(F)`

**geo-m3-t1-l3-act36-midsegment-theorem-1** `midsegment, midpoint, parallel-lines, triangle`

> Draw triangle ABC where M is the midpoint of side AB and N is the midpoint of side AC. Connect M and N with a segment to show the midsegment. Mark M as the midpoint of AB with a tick mark on AM and MB to show they're equal. Mark N as the midpoint of AC with a tick mark on AN and NC. Show that MN is parallel to BC using arrow marks on both segments. Also label BC = 10 and MN = 5 to show the midsegment is half the length of BC.

Labels: A, B, C, M, N
Properties: `midpoint(M, A, B)`, `midpoint(N, A, C)`, `parallel(['M', 'N'], ['B', 'C'])`, `equal_lengths(['A', 'M'], ['M', 'B'])`, `equal_lengths(['A', 'N'], ['N', 'C'])`, `label_present(M)`, `label_present(N)`

**geo-m3-t1-l4-act41-geometric-mean-altitude-theorem-1** `geometric-mean, altitude-theorem, right-triangle, hypotenuse`

> Draw right triangle ABC with the right angle at C. Drop an altitude from C to the hypotenuse AB and label the foot of the altitude as D. Label segment AD = 4 and segment DB = 9. Label the altitude CD as 'h'. Show me the proportion that gives the geometric mean: AD/CD = CD/DB, which means h squared equals 4 times 9. Mark the right angle at C and the right angle at D where the altitude meets the hypotenuse.

Labels: A, B, C, D
Properties: `right_angle(A, C, B)`, `right_angle(A, D, C)`, `point_on_segment(D, A, B)`, `perpendicular(['C', 'D'], ['A', 'B'])`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m3-t1-l5-act51-mirror-indirect-measurement-1** `indirect-measurement, similar-triangles, AA-similarity, law-of-reflection`

> Draw a diagram showing a person standing at point A, a mirror flat on the ground at point M, and the base of a tall flagpole at point F directly across from the mirror. The person's eye is at point E (above A), and the top of the flagpole is at point T (above F). Draw the reflected sight line from E down to the mirror at M and then up to T. Mark the angle of incidence and angle of reflection at M as equal. Show the two right triangles: triangle EAM (person's right triangle) and triangle TFM (flagpole's right triangle). Label the person's eye height EA = 5 ft, the distance from person to mirror AM = 4 ft, and the distance from mirror to flagpole MF = 20 ft.

Labels: A, E, M, F, T
Properties: `right_angle(E, A, M)`, `right_angle(T, F, M)`, `angle_equal(['E', 'M', 'A'], ['T', 'M', 'F'])`, `mark_present(right_angle, A)`, `mark_present(right_angle, F)`, `label_present(M)`, `label_present(E)`, `label_present(T)`

**geo-m3-t1-l5-act52-shadow-similar-triangles-1** `indirect-measurement, shadow-method, similar-triangles, AA-similarity`

> Draw a diagram for the shadow method of indirect measurement. Show a vertical stick at point A with height AB = 2 feet, casting a shadow along the ground from A to S where AS = 3 feet. Next to it, show a tall tree at point C with unknown height CD, casting a shadow from C to T where CT = 15 feet. Mark the right angles at the bases B and D (where the objects meet the ground). The sunlight rays hit both objects at the same angle, so mark angle S and angle T as equal. Label everything and put a question mark on CD to show it's unknown.

Labels: A, B, S, C, D, T
Properties: `right_angle(A, B, S)`, `right_angle(C, D, T)`, `angle_equal(['B', 'S', 'A'], ['D', 'T', 'C'])`, `perpendicular(['A', 'B'], ['B', 'S'])`, `perpendicular(['C', 'D'], ['D', 'T'])`, `label_present(S)`, `label_present(T)`

**geo-m3-t1-l6-act61-trisecting-segment-construction-1** `segment-division, triangle-proportionality, construction, parallel-lines`

> Draw a line segment AB. From point A, draw an auxiliary ray going diagonally upward and use compass arcs to mark three equal segments on that ray, labeling the points P1, P2, and P3 where P3 is the endpoint. Connect P3 to B. Then draw lines through P1 and P2 that are parallel to P3B, hitting segment AB at points Q1 and Q2. This construction trisects AB so that AQ1 = Q1Q2 = Q2B. Mark all three equal parts on AB.

Labels: A, B, P1, P2, P3, Q1, Q2
Properties: `equal_lengths(['A', 'P1'], ['P1', 'P2'])`, `equal_lengths(['P1', 'P2'], ['P2', 'P3'])`, `parallel(['P1', 'Q1'], ['P3', 'B'])`, `parallel(['P2', 'Q2'], ['P3', 'B'])`, `equal_lengths(['A', 'Q1'], ['Q1', 'Q2'])`, `equal_lengths(['Q1', 'Q2'], ['Q2', 'B'])`, `point_on_segment(Q1, A, B)`, `point_on_segment(Q2, A, B)`

**geo-m3-t1-l6-act62-directed-segment-partition-coordinate-1** `directed-line-segment, partitioning, coordinate-plane, proportionality`

> On a coordinate plane, draw a directed line segment from point A at (1, 1) to point B at (7, 5). I need to find the point P that is 1/3 of the way from A to B. Draw auxiliary horizontal and vertical dashed lines from A and B to make a right triangle, labeling the right angle corner as C at (7, 1). Show that the horizontal distance AC = 6 and vertical distance BC = 4. Mark point P on segment AB at 1/3 of the way and label its coordinates. Draw dashed lines from P showing how it relates to 1/3 of the horizontal and vertical distances.

Labels: A, B, C, P
Properties: `right_angle(A, C, B)`, `point_on_segment(P, A, B)`, `perpendicular(['A', 'C'], ['B', 'C'])`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(P)`, `collinear(A, P, B)`

**geo-m4-t1-l1-act11-similar-triangles-chords-1** `circles, chords, similar-triangles, AA-similarity`

> Draw a circle with two chords AC and BD that intersect inside the circle at point P. Then draw the triangles formed by connecting A to B and D to C. I need to see triangle APB and triangle DPC highlighted so I can prove they're similar using AA similarity. Label all five points A, B, C, D, and P, and mark the pairs of equal inscribed angles — angle PAB equals angle PDC, and angle PBA equals angle PCD.

Labels: A, B, C, D, P
Properties: `point_on_segment(P, A, C)`, `point_on_segment(P, B, D)`, `angle_equal(['A', 'P', 'B'], ['D', 'P', 'C'])`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(P)`

**geo-m4-t1-l1-act12-tangent-secant-external-1** `circles, tangent, secant, external-point, secant-tangent-theorem`

> Draw a circle with a point P outside it. Draw one tangent line from P that just touches the circle at point T, and one secant from P that passes through the circle at points A and B, where A is closer to P. Label PT = 6, PA = 3, and PB = 12. I want to see that PT squared equals PA times PB. Also mark the right angle between the radius to T and the tangent line PT.

Labels: P, T, A, B
Properties: `tangent(['P', 'T'], O, T)`, `point_on_segment(A, P, B)`, `label_present(P)`, `label_present(T)`, `label_present(A)`, `label_present(B)`

**geo-m4-t1-l1-act12-two-secants-external-1** `circles, secants, external-point, secant-segment-theorem`

> Draw a circle and a point P outside the circle. Draw two secant lines from P through the circle. The first secant hits the circle at points A and B (with A closer to P), and the second secant hits the circle at points C and D (with C closer to P). Label PA = 4, PB = 9, PC = 3, and PD = 12 so I can see that PA times PB equals PC times PD. I also need the external secant segments PA and PC labeled clearly.

Labels: P, A, B, C, D
Properties: `label_present(P)`, `point_on_segment(A, P, B)`, `point_on_segment(C, P, D)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m4-t1-l2-act21-circle-similarity-dilation-1** `circles, similarity, dilation, transformations`

> Draw two circles of different sizes — a small circle centered at point A with radius 2 and a larger circle centered at point B with radius 5. Show a dilation that maps the small circle onto the large circle with a scale factor of 5/2. Draw an arrow or dashed line indicating the translation from A to B, and label both centers and both radii so I can see how one circle maps onto the other.

Labels: A, B
Properties: `label_present(A)`, `label_present(B)`

**geo-m4-t1-l2-act22-arc-length-two-circles-1** `circles, arc-length, central-angle, proportional-reasoning`

> Draw two separate circles side by side. The first circle has radius r = 3 and the second has radius r = 6. In each circle, draw a central angle of 60 degrees and shade the arc it cuts off. Label the central angle 60° in both circles, label the radii, and label the arc length on each circle using the formula s = (60/360)(2πr) so I can compare how the arc lengths differ even though the central angles are the same.

Labels: O, A, B
Properties: `angle_equal(['A', 'O', 'B'], ['A', 'O', 'B'])`, `label_present(O)`

**geo-m4-t1-l2-act23-radian-unit-circle-1** `circles, radians, arc-length, unit-circle, angle-measure`

> Draw a unit circle centered at point O with radius 1. Mark four points on the circle at 90°, 180°, 270°, and 360° (back to start) and label them A, B, C, and D. At each of those points write the radian measure — π/2, π, 3π/2, and 2π. Shade the arc from the starting point to each labeled point and show the central angle θ at the center for the arc from start to A.

Labels: O, A, B, C, D
Properties: `label_present(O)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `right_angle(A, O, D)`

**geo-m4-t1-l3-act32-segment-area-60deg-1** `circles, segment-area, sector, equilateral-triangle, 60-degree`

> Draw a circle with center O and radius 6. Draw two radii OA and OB forming a central angle of 60 degrees. Connect A and B with a chord to make triangle OAB. Shade the circular segment between chord AB and the shorter arc AB. Since angle AOB is 60° and OA = OB = 6, triangle OAB is equilateral — so label all three sides as 6 and mark all three 60° angles. I want to find the shaded segment area by subtracting the triangle area from the sector area.

Labels: O, A, B
Properties: `equal_lengths(['O', 'A'], ['O', 'B'])`, `equal_lengths(['O', 'A'], ['O', 'B'], ['A', 'B'])`, `label_present(O)`, `label_present(A)`, `label_present(B)`

**geo-m4-t1-l3-act32-segment-area-90deg-1** `circles, segment-area, sector, triangle, 90-degree`

> Draw a circle with center O and radius 8. Draw a chord AB so that the central angle AOB is exactly 90 degrees. Shade the circular segment between chord AB and the arc AB (the smaller region). Draw the triangle OAB inside the sector. I need to find the segment area by doing: area of sector AOB minus area of triangle OAB. Mark the right angle at O and label OA = OB = 8.

Labels: O, A, B
Properties: `right_angle(A, O, B)`, `equal_lengths(['O', 'A'], ['O', 'B'])`, `label_present(O)`, `label_present(A)`, `label_present(B)`

**geo-m4-t1-l3-gs-sectors-parallelogram-1** `circles, sectors, area, informal-proof`

> Draw two side-by-side figures. On the left, draw a circle divided into 20 congruent sectors like a pizza, with center O and radius r labeled. On the right, show those same sectors rearranged into a shape that looks like a parallelogram — with the sectors alternating point-up and point-down. Label the base of the parallelogram as πr and the height as r, so I can see why the area of the circle is πr².

Labels: O
Properties: `label_present(O)`

**geo-m4-t1-l4-act42-completing-square-circle-1** `circles, coordinate-geometry, completing-the-square, general-form`

> Draw a coordinate plane with a circle centered at (2, 3) with radius 2. Label the center point as C = (2, 3) and mark the radius as 2 units. Draw a horizontal and vertical line through the center to show where the circle crosses — it should reach x = 0, x = 4, y = 1, and y = 5. This matches the equation (x − 2)² + (y − 3)² = 4, which comes from completing the square on the general form. Label those four edge points.

Labels: C
Properties: `label_present(C)`

**geo-m4-t1-l4-gs-circle-equation-center-hk-1** `circles, coordinate-geometry, pythagorean-theorem, standard-form`

> Draw a coordinate plane with a circle centered at point C = (h, k) — use h = 3 and k = 2 as actual numbers. Pick a point P = (x, y) on the circle. Draw the right triangle from C to a point F directly below P at (x, k), then up to P. Label the horizontal leg as (x − h), the vertical leg as (y − k), and the hypotenuse as r. Mark the right angle at F. This should show me where (x − h)² + (y − k)² = r² comes from.

Labels: C, F, P
Properties: `right_angle(C, F, P)`, `label_present(C)`, `label_present(F)`, `label_present(P)`, `collinear(C, F, C)`

**geo-m4-t1-l4-gs-circle-equation-origin-1** `circles, coordinate-geometry, pythagorean-theorem, equation-of-circle`

> Draw a coordinate plane with a circle centered at the origin O. Pick a point (x, y) on the circle and draw a right triangle with the right angle at point F = (x, 0) on the x-axis. The legs go from O to F along the x-axis (length x) and from F straight up to the point (x, y) (length y), and the hypotenuse goes from O to (x, y) — that's the radius r. Label all three sides x, y, and r, and mark the right angle at F. Write x² + y² = r² next to the triangle.

Labels: O, F
Properties: `right_angle(O, F, P)`, `label_present(O)`, `label_present(F)`, `collinear(O, F, P)`

**geo-m4-t1-l5-act51-points-on-circle-origin-1** `circles, coordinate-geometry, points-on-circle, pythagorean-theorem`

> Draw a coordinate plane with a circle centered at origin O with radius 5. Plot three candidate points: P1 = (3, 4), P2 = (4, 4), and P3 = (−3, 4). For each point draw a right triangle from the origin to the point, with legs along the x and y directions. I want to check which ones satisfy x² + y² = 25. Label all three points and mark the right angle at the base of each triangle.

Labels: O, P1, P2, P3
Properties: `point_on_circle(P1, O, P1)`, `label_present(O)`, `label_present(P1)`, `label_present(P2)`, `label_present(P3)`

**geo-m4-t1-l5-act52-circle-not-at-origin-1** `circles, coordinate-geometry, points-on-circle, off-origin-center`

> Draw a coordinate plane with a circle centered at point C = (−2, −3) with radius 5. Plot two candidate points: Q1 = (2, 0) and Q2 = (1, 1). For each candidate point, draw a right triangle from the center C to the candidate point with horizontal and vertical legs. I want to check whether each point is on the circle by seeing if the distance from C equals 5. Label C, Q1, Q2, and mark the right angles in the triangles.

Labels: C, Q1, Q2
Properties: `point_on_circle(Q1, C, Q1)`, `label_present(C)`, `label_present(Q1)`, `label_present(Q2)`

**geo-m4-t2-l1-a11-rotation-solids-1** `rotation, cylinder, cone, sphere, 2d-to-3d`

> Draw three side-by-side diagrams showing 2D shapes spinning around a vertical axis to form 3D solids. First: a rectangle with width r and height h spinning to form a cylinder — label r and h on both the rectangle and the cylinder. Second: a semicircle with radius r spinning around its flat diameter edge to form a sphere — label r on both. Third: a right triangle with legs r and h spinning around the leg of length h to form a cone — label r and h on both the triangle and the cone. Draw arrows showing the direction of rotation for each.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `right_angle(r_point, vertex, h_point)`

**geo-m4-t2-l1-a12-stacking-shapes-1** `stacking, prism, cylinder, 3d-solids`

> Draw three stacking diagrams side by side. First: a stack of congruent circles (about 5 of them) forming a cylinder — label the radius r on the bottom circle and the total height h. Second: a stack of congruent squares forming a right rectangular prism — label side length s on the bottom square and height h. Third: a stack of congruent equilateral triangles forming a triangular prism — label the base b and height of the triangle on the bottom face, and overall prism height h. Use dashed lines to show the interior edges.

Labels: r, h, s, b
Properties: `label_present(r)`, `label_present(h)`, `label_present(s)`, `equal_lengths(['r1', 'center1'], ['r2', 'center2'])`

**geo-m4-t2-l1-a13-right-oblique-prisms-1** `isometric, prism, oblique, right-prism, translation`

> On isometric dot paper, draw two triangular prisms side by side. The first one should be a right triangular prism where triangle ABC is the base and the lateral edges go straight up vertically to points D, E, F directly above A, B, C. The second one should be an oblique triangular prism where triangle ABC is the base but the top triangle GHI is shifted diagonally so the lateral edges are slanted. Label all vertices on both prisms and mark the lateral faces. Use dashed lines for hidden edges.

Labels: A, B, C, D, E, F, G, H, I
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(E)`, `label_present(F)`, `perpendicular(['A', 'D'], ['A', 'B'])`, `equal_lengths(['A', 'D'], ['B', 'E'], ['C', 'F'])`

**geo-m4-t2-l1-a13-right-oblique-prisms-2** `isometric, prism, rectangular, oblique, right-prism`

> On isometric dot paper, draw a right rectangular prism with base ABCD and top face EFGH, where E is above A, F is above B, G is above C, and H is above D. Label all 8 vertices. Then next to it draw an oblique rectangular prism with the same base ABCD but with the top face shifted so it's not directly above — label the top vertices as P, Q, R, S. Mark the lateral faces as parallelograms on the oblique version. Use dashed lines for hidden edges on both.

Labels: A, B, C, D, E, F, G, H, P, Q, R, S
Properties: `label_present(A)`, `label_present(E)`, `label_present(P)`, `perpendicular(['A', 'E'], ['A', 'B'])`, `parallel(['A', 'B'], ['E', 'F'])`, `parallel(['A', 'B'], ['P', 'Q'])`

**geo-m4-t2-l1-a14-cylinder-disc-stack-1** `cylinder, volume, disc, cross-section`

> Draw a cylinder with radius r and height h, then show it being built by stacking a bunch of thin disc cross-sections on top of each other. Label one disc with area = π r². Draw a horizontal dashed line through the middle of the cylinder to show where one disc sits, and label its thickness as a tiny value. Also label the total height h and radius r on the cylinder. I want to see how the volume formula V = πr²h comes from stacking all those discs.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `mark_present(cross_section, O)`

**geo-m4-t2-l1-gs-rectangle-rotation-1** `rotation, 3d-solids, cylinder, transformation`

> Can you draw a rectangle ABCD where AB is the top edge, DC is the bottom edge, and DC lies on a vertical axis? Then show the rectangle rotating around that axis to trace out a cylinder. Label the axis, mark the radius as the width of the rectangle (from the axis to point B), and show the resulting cylinder with height equal to AD. I want to see both the original rectangle and the 3D cylinder it creates.

Labels: A, B, C, D
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `collinear(D, C, axis_point)`, `right_angle(A, D, C)`, `right_angle(D, C, B)`

**geo-m4-t2-l1-tt-cone-rotation-1** `rotation, cone, right-triangle, volume`

> Draw right triangle ABC where angle C is 90 degrees, leg BC has length r (the radius), and leg AC has length h (the height). Show the triangle rotating around leg AC (the vertical leg) to form a cone. Draw the resulting cone next to the triangle with radius r at the base and height h, and label both dimensions on the cone too. Mark the right angle at C and draw an arrow showing the direction of rotation.

Labels: A, B, C, r, h
Properties: `right_angle(A, C, B)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(r)`, `label_present(h)`, `collinear(A, C, axis_bottom)`

**geo-m4-t2-l2-a21-plane-intersections-1** `cross-section, cone, sphere, plane, intersection`

> Draw two diagrams of a cone. In the first diagram, show a horizontal plane touching just the very tip (apex) of the cone at point P to produce a single point cross-section — label the apex P. In the second diagram, show a vertical plane cutting through the cone passing exactly through the apex and two sides, making a triangular cross-section — label the apex V and the two base intersection points A and B. Mark the cross-sections clearly.

Labels: P, V, A, B
Properties: `label_present(P)`, `label_present(V)`, `label_present(A)`, `label_present(B)`, `point_on_line(V, A, B)`

**geo-m4-t2-l2-a22-cylinder-cross-sections-1** `cross-section, cylinder, circle, ellipse, rectangle`

> Draw three copies of the same cylinder with radius r and height h. On the first cylinder, draw a horizontal cutting plane parallel to the base that creates a circular cross-section — shade the circle and label it 'circle cross-section'. On the second cylinder, draw a vertical cutting plane perpendicular to the base that creates a rectangular cross-section — shade the rectangle and label its dimensions 2r by h. On the third cylinder, draw a diagonal cutting plane at an angle that creates an elliptical cross-section — shade the ellipse and label it 'ellipse cross-section'. Label r and h on each cylinder.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `parallel(['A', 'B'], ['C', 'D'])`, `perpendicular(['E', 'F'], ['G', 'H'])`

**geo-m4-t2-l2-tt-pentagonal-pyramid-cross-sections-1** `cross-section, pyramid, pentagon, rectangle`

> Draw two diagrams of the same pentagonal pyramid with apex V and pentagonal base ABCDE. In the first diagram, draw a horizontal cutting plane parallel to the base ABCDE that slices through the pyramid about halfway up — shade the pentagonal cross-section and label it. In the second diagram, draw a vertical cutting plane perpendicular to the base that passes through apex V and the midpoint of edge AB — shade the triangular cross-section and label its three vertices. Label V, A, B, C, D, E on both pyramids.

Labels: V, A, B, C, D, E
Properties: `label_present(V)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(E)`, `parallel(['A', 'B'], ['cross1', 'cross2'])`

**geo-m4-t2-l3-a31-cube-pyramid-layers-1** `pyramid, prism, volume, ratio, centimeter-cubes`

> Draw two diagrams side by side. First: a 3-layer staircase pyramid made of centimeter cubes — the bottom layer is a 3×3 arrangement of cubes, the middle layer is a 2×2 arrangement, and the top layer is a single cube. Label the total height as 3 units and the base as 3×3. Second: the corresponding rectangular prism that has the same 3×3 base and height of 3 units. Label all dimensions. I want to compare the volume of the pyramid (which is about 1/3 of the prism) vs. the full prism.

Labels: height, base
Properties: `label_present(height)`, `label_present(base)`, `equal_lengths(['A', 'B'], ['C', 'D'])`

**geo-m4-t2-l3-a32-cone-cylinder-comparison-1** `cone, cylinder, volume, comparison`

> Draw a cylinder and a cone side by side where both have exactly the same base radius r and the same height h. Label r and h on both. On the cylinder write V = πr²h, and on the cone write V = (1/3)πr²h. Draw a bracket or arrow showing that the cone's volume is exactly 1/3 of the cylinder's volume. Mark the right angle where the height meets the base on both shapes.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `equal_lengths(['O1', 'r1'], ['O2', 'r2'])`, `equal_lengths(['h1_bottom', 'h1_top'], ['h2_bottom', 'h2_top'])`, `right_angle(top_center, O1, edge_r)`, `right_angle(apex, O2, edge_r2)`

**geo-m4-t2-l3-gs-stacking-pyramids-1** `pyramid, cone, stacking, similar-shapes, volume`

> Draw three stacking diagrams side by side showing how similar shapes of decreasing size build 3D solids. First: stack about 6 circles that get smaller from bottom to top to form a cone — label the bottom circle's radius r and the total height h. Second: stack about 6 squares that get smaller from bottom to top to form a square pyramid — label the bottom square's side length s and total height h. Third: stack about 6 equilateral triangles that decrease in size from bottom to top to form a triangular pyramid — label the bottom triangle's base b and total height h. Draw dashed outlines connecting the edges to show the solid shapes.

Labels: r, h, s, b
Properties: `label_present(r)`, `label_present(h)`, `label_present(s)`, `label_present(b)`

**geo-m4-t2-l4-a41-cone-net-1** `net, cone, surface-area, slant-height, lateral-face`

> Draw the net (unfolded surface) of a right cone with base radius r, height h, and slant height s. The net should show a circular sector (the unrolled lateral surface) with radius equal to slant height s, and a circle of radius r (the base) attached below. Label s as the slant height on the sector's curved edge, label r on the base circle, and label the arc length of the sector as 2πr. Write the lateral surface area formula = πrs and total surface area formula = πr² + πrs. Also draw a small right triangle next to it showing how s relates to r and h using the Pythagorean theorem: s² = r² + h².

Labels: r, h, s
Properties: `label_present(r)`, `label_present(h)`, `label_present(s)`, `right_angle(h_top, base_center, r_edge)`, `mark_present(slant_height, s)`

**geo-m4-t2-l4-a41-cylinder-net-1** `net, cylinder, surface-area, lateral-face`

> Draw the net (unfolded surface) of a right cylinder with radius r and height h. The net should show a large rectangle (the lateral face) with width equal to the circumference 2πr and height h, with one circle of radius r attached to the top edge and another circle of radius r attached to the bottom edge. Label the rectangle dimensions as 2πr and h, label r on each circle, and write the area formulas: rectangle area = 2πrh, each circle area = πr². Also write the total surface area formula SA = 2πr² + 2πrh at the bottom.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `equal_lengths(['O1', 'P1'], ['O2', 'P2'])`, `mark_present(circumference_label, rectangle_top)`

**geo-m4-t2-l4-a41-square-pyramid-net-1** `net, pyramid, surface-area, slant-height, triangular-face`

> Draw the net (unfolded surface) of a right square pyramid with square base side length ℓ and slant height s. The net should show the square base ABCD in the middle, with four congruent isosceles triangles unfolded outward — one on each side of the square. Label the square side as ℓ and the slant height (triangle height) as s on each triangular face. Mark that all four triangles are congruent with tick marks. Write the lateral surface area formula = 2ℓs and total surface area formula = ℓ² + 2ℓs at the bottom.

Labels: A, B, C, D, s, ℓ
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(s)`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'A'])`, `equal_lengths(['apex1', 'mid1'], ['apex2', 'mid2'], ['apex3', 'mid3'], ['apex4', 'mid4'])`, `right_angle(D, A, B)`

**geo-m4-t2-l4-gs-rotation-lateral-faces-1** `rotation, cylinder, cone, lateral-face, surface-area`

> Draw three rotation diagrams. First: rectangle ABCD with DC on the axis of rotation — show it rotating to form a cylinder, and highlight the rectangular lateral face in a different color. Label A, B, C, D and mark the axis along DC. Second: right triangle DEF with EF on the axis of rotation — show it rotating to form a cone, and highlight the curved lateral surface. Label D, E, F. Third: rectangle JKLM rotating about an external vertical axis (not touching the rectangle) — show the resulting hollow cylinder (like a tube). Label J, K, L, M and show the axis to the left of J.

Labels: A, B, C, D, E, F, J, K, L, M
Properties: `label_present(A)`, `label_present(D)`, `label_present(E)`, `label_present(F)`, `label_present(J)`, `label_present(M)`, `collinear(D, C, axis_point)`, `collinear(E, F, axis_point2)`, `right_angle(A, D, C)`

**geo-m4-t2-l4-tt-cone-slant-height-1** `cone, slant-height, pythagorean-theorem, surface-area`

> Draw a right cone with apex V at the top, center of base O, and a point on the base edge labeled A. Label the height VO = 8 (a vertical dashed line from V straight down to O), the radius OA = 6, and the slant height VA = s (a solid line from the apex to the base edge). Inside the cone, highlight the right triangle VOA where the right angle is at O. Show the calculation s² = 6² + 8² = 100 so s = 10 next to the diagram. Then write the lateral surface area = πrs = π(6)(10) = 60π next to it.

Labels: V, O, A, s
Properties: `label_present(V)`, `label_present(O)`, `label_present(A)`, `label_present(s)`, `right_angle(V, O, A)`, `perpendicular(['V', 'O'], ['O', 'A'])`, `point_on_segment(O, V, A)`

## Tier 3: Multi-step / Advanced (37 scenarios)

**geo-m1-t1-l2-a22-spherical-triangle-1** `spherical-geometry, great-circle, non-euclidean, angle-sum`

> Draw a sphere and show three great circles on it that form a triangle on the surface. Label the three vertices of the spherical triangle as A, B, and C. Make each angle of the triangle look like it's 90 degrees — so this is a triangle where all three angles are right angles, which is possible on a sphere but not in flat geometry. Mark each right angle with a small square. I want this to illustrate how spherical geometry is different from Euclidean geometry.

Labels: A, B, C
Properties: `right_angle(B, A, C)`, `right_angle(A, B, C)`, `right_angle(A, C, B)`, `mark_present(right_angle, A)`, `mark_present(right_angle, B)`, `mark_present(right_angle, C)`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m1-t1-l3-a35-auxiliary-lines-grid-1** `auxiliary-line, right-triangle, pythagorean-theorem, deductive-reasoning, grid`

> Draw a 2×3 grid of congruent squares — 2 rows and 3 columns. Label the corners of the grid. The top-left corner is A, going right along the top: B, C, D. The middle row left to right: E, F, G. The bottom row: H, I, J, K — wait, let me just label key points. Top-left is A, the internal vertices along the bottom of the top row are at I and K, and the far corners are labeled. Draw dashed auxiliary line segments from A to create the diagonals of the triangles used in the proof — specifically draw dashed lines from A to the key internal vertices to form triangles. Mark the right angles at the square corners. I want this to show how auxiliary lines help us reason about the angle sum conjecture from the three-squares activity.

Labels: A, I, K, E, G
Properties: `label_present(A)`, `label_present(I)`, `label_present(K)`, `label_present(E)`, `label_present(G)`, `right_angle(A, I, K)`, `point_on_segment(I, A, I)`, `point_on_segment(K, A, K)`

**geo-m1-t3-l3-act35-sequence-reflection-translation-1** `reflection, translation, sequence-of-transformations, congruence`

> Draw two congruent triangles ABC and A'B'C' in different positions on a plane (not on a coordinate grid). Show a sequence of transformations mapping ABC to A'B'C': first draw dashed segments connecting A to A', B to B', C to C', mark their midpoints, and draw the perpendicular bisector through those midpoints as the line of reflection. Then show a small arrow indicating a translation to finish mapping the reflected figure to A'B'C'. Label all six vertices and the line of reflection as line ℓ.

Labels: A, B, C, A', B', C'
Properties: `equal_lengths(['A', 'B'], ["A'", "B'"])`, `equal_lengths(['B', 'C'], ["B'", "C'"])`, `label_present(A')`, `midpoint(M, A, A')`, `perpendicular(['A', "A'"], ['B', "B'"])`

**geo-m1-t3-l4-act43-center-of-rotation-perpendicular-bisectors-1** `rotation, center-of-rotation, perpendicular-bisector, construction`

> Draw triangle ABC and its rotated image A'B'C' somewhere on the plane without a grid. Connect A to A' with a dashed segment and find its midpoint, then draw the perpendicular bisector of AA'. Do the same for B to B'. Show where the two perpendicular bisectors intersect and label that intersection point O — that's the center of rotation. Draw arcs from A to A' and B to B' centered at O to show the angle of rotation. Label all six vertices, the midpoints, and O.

Labels: A, B, C, A', B', C', O
Properties: `midpoint(M1, A, A')`, `midpoint(M2, B, B')`, `perpendicular(['A', "A'"], ['M1', 'O'])`, `perpendicular(['B', "B'"], ['M2', 'O'])`, `equal_lengths(['O', 'A'], ['O', "A'"])`, `equal_lengths(['O', 'B'], ['O', "B'"])`, `label_present(O)`

**geo-m1-t3-l4-act44-sequence-rigid-motions-congruence-1** `sequence-of-transformations, rotation, reflection, translation, congruence`

> Draw two congruent triangles XYZ and X'Y'Z' in different positions and orientations on a plane. Show a three-step sequence that maps XYZ onto X'Y'Z': first draw a dashed arrow showing a translation, then draw a line of reflection ℓ with the reflected intermediate triangle X''Y''Z'', then show a rotation arc about a center point O to finish mapping to X'Y'Z'. Label all nine vertices X, Y, Z, X', Y', Z', X'', Y'', Z'', the line ℓ, and rotation center O.

Labels: X, Y, Z, X', Y', Z', X'', Y'', Z'', O
Properties: `equal_lengths(['X', 'Y'], ["X'", "Y'"])`, `equal_lengths(['X', 'Y'], ["X''", "Y''"])`, `equal_lengths(['O', "X''"], ['O', "X'"])`, `label_present(O)`, `label_present(X'')`

**geo-m1-t3-l5-act51-composition-reflection-translation-triangle-1** `composition, reflection, translation, coordinate-plane`

> On a coordinate plane draw triangle ABC with A at (-3, 1), B at (-1, 1), C at (-2, 3). First reflect it across the y-axis to get A'B'C'. Then translate A'B'C' by 1 unit right and 2 units down to get A''B''C''. Draw and label all three triangles — the original, the reflected one, and the final image. Label all nine vertices and the y-axis as the line of reflection.

Labels: A, B, C, A', B', C', A'', B'', C''
Properties: `equal_lengths(['A', 'B'], ["A'", "B'"])`, `equal_lengths(['A', 'B'], ["A''", "B''"])`, `parallel(["A'", "A''"], ["B'", "B''"])`, `equal_lengths(["A'", "A''"], ["B'", "B''"])`, `label_present(A'')`, `label_present(A')`

**geo-m1-t3-l5-act52-composition-rotation-reflection-parallelogram-1** `composition, rotation, reflection, translation, parallelogram, coordinate-plane`

> Draw parallelogram PQRS on a coordinate plane with P at (1,0), Q at (3,0), R at (4,2), S at (2,2). First rotate PQRS 90 degrees counterclockwise about the origin to get P'Q'R'S'. Then reflect P'Q'R'S' across the x-axis to get P''Q''R''S''. Label all twelve vertices and mark the origin O. I want to see the whole composition laid out step by step.

Labels: P, Q, R, S, P', Q', R', S', P'', Q'', R'', S'', O
Properties: `equal_lengths(['P', 'Q'], ["P'", "Q'"])`, `equal_lengths(['P', 'Q'], ["P''", "Q''"])`, `equal_lengths(['O', 'P'], ['O', "P'"])`, `label_present(O)`, `label_present(P'')`, `parallel(['P', 'Q'], ['S', 'R'])`, `parallel(["P'", "Q'"], ["S'", "R'"])`

**geo-m1-t3-l5-ttt-composition-three-step-rectangle-1** `composition, reflection, rotation, translation, rectangle, coordinate-plane`

> Draw rectangle EFGH on a coordinate plane with E at (1,1), F at (3,1), G at (3,2), H at (1,2). Apply a three-step composition: step 1 — reflect across the x-axis to get E'F'G'H'; step 2 — rotate 90 degrees counterclockwise about the origin to get E''F''G''H''; step 3 — translate 2 units up to get E'''F'''G'''H'''. Draw and label all four versions of the rectangle and mark the origin O.

Labels: E, F, G, H, E', F', G', H', E'', F'', G'', H'', E''', F''', G''', H''', O
Properties: `equal_lengths(['E', 'F'], ["E'", "F'"])`, `equal_lengths(['E', 'F'], ["E''", "F''"])`, `equal_lengths(['E', 'F'], ["E'''", "F'''"])`, `equal_lengths(['O', "E'"], ['O', "E''"])`, `parallel(["E''", "E'''"], ["F''", "F'''"])`, `equal_lengths(["E''", "E'''"], ["F''", "F'''"])`, `label_present(E''')`

**geo-m1-t4-l2-sas-proof-circle-1** `SAS, congruence-proof, reflection, circle`

> Draw two triangles ABC and DEF where AB = DE (mark with one tick), angle B = angle E (mark with one arc), and BC = EF (mark with two ticks). Then in a separate diagram, show the SAS reflection proof step where we've already mapped segment AB onto segment DE, so now we're looking at point C and point F. Draw a circle centered at E with radius equal to BC (= EF), and show two dashed lines from E to two possible positions where C' (the image of C) could land on the circle. Label the two possible positions C'1 and C'2. This shows why the included angle matters for pinning down the unique location.

Labels: A, B, C, D, E, F, C'1, C'2
Properties: `equal_lengths(['A', 'B'], ['D', 'E'])`, `equal_lengths(['B', 'C'], ['E', 'F'])`, `angle_equal(['A', 'B', 'C'], ['D', 'E', 'F'])`, `point_on_circle(C'1, E, F)`, `point_on_circle(C'2, E, F)`, `label_present(E)`, `label_present(F)`

**geo-m1-t4-l2-ssa-ambiguity-1** `SSA, ambiguous-case, circle-construction, non-congruence`

> Draw an SSA ambiguity diagram to show why SSA doesn't prove congruence. Start with a base angle at vertex A — draw a ray from A. Mark a side length AB = 8 units along the ray and mark angle A = 40 degrees. Now from point B, draw a circle with radius 5 units. Show that this circle intersects the other ray from A at TWO different points — label them C1 and C2. This gives two different triangles: ABC1 and ABC2, both with the same angle at A, same side AB, and same length BC, but the triangles are different shapes. Label all points.

Labels: A, B, C1, C2
Properties: `point_on_circle(C1, B, C1)`, `point_on_circle(C2, B, C2)`, `equal_lengths(['B', 'C1'], ['B', 'C2'])`, `label_present(A)`, `label_present(B)`, `label_present(C1)`, `label_present(C2)`

**geo-m1-t4-l3-bridge-indirect-measurement-1** `SAS, vertical-angles, indirect-measurement, real-world`

> Draw a river-crossing indirect measurement diagram. Show a horizontal river with two banks. On the top bank label two points: A (at the edge of the river) and B (further from the river). On the bottom bank label point C directly across from A. Draw triangle ABC where AB goes inland and BC is the width of the river — that's the unknown length. Now extend segment CA past A to a point D on the same bank as B, so that A is between C and D. Also mark point E on the bottom bank so that triangle DAE is on the land side. Mark CA = DA (one tick each) and angle CAB = angle DAE as vertical angles (one arc each), and AB = AE (two ticks each). This sets up SAS congruence so DE = BC.

Labels: A, B, C, D, E
Properties: `equal_lengths(['C', 'A'], ['D', 'A'])`, `equal_lengths(['A', 'B'], ['A', 'E'])`, `collinear(C, A, D)`, `angle_equal(['C', 'A', 'B'], ['D', 'A', 'E'])`, `equal_lengths(['D', 'E'], ['B', 'C'])`, `label_present(A)`, `label_present(B)`, `label_present(C)`

**geo-m1-t4-l3-camera-sas-floorplan-1** `SAS, real-world, right-angle, reflexive-property`

> Draw a rectangular store floor plan with corners labeled W (top-left), X (top-right), Y (bottom-right), Z (bottom-left). Place a camera position point C at the midpoint of the top wall WX. Draw lines of sight from C down to two points A and B on the bottom wall ZY, where A and B are equidistant from the center of ZY — label the center of ZY as M. Mark CA = CB with tick marks, angle CAM = angle CBM with arc marks, and AM = BM with tick marks. This sets up SAS congruence for triangles CAM and CBM so the cameras cover equal areas.

Labels: W, X, Y, Z, C, A, B, M
Properties: `midpoint(C, W, X)`, `midpoint(M, Z, Y)`, `equal_lengths(['A', 'M'], ['B', 'M'])`, `equal_lengths(['C', 'A'], ['C', 'B'])`, `perpendicular(['C', 'M'], ['Z', 'Y'])`, `right_angle(C, M, A)`, `right_angle(C, M, B)`, `label_present(C)`, `label_present(M)`

**geo-m1-t4-l3-coordinate-plane-triangles-1** `coordinate-plane, SSS, distance-formula, rigid-motion`

> Plot two triangles on a coordinate plane to show they're congruent by SSS. Draw triangle ABC with A at (1, 1), B at (4, 1), and C at (4, 5). Then draw triangle DEF with D at (-1, -1), E at (-4, -1), and F at (-4, -5). Label all six points with their coordinates. Draw dashed tick marks to show AB = DE, BC = EF, and AC = DF. Also draw a dashed arrow showing that triangle ABC can be mapped onto triangle DEF by a reflection across the origin or a 180-degree rotation.

Labels: A, B, C, D, E, F
Properties: `right_angle(A, B, C)`, `right_angle(D, E, F)`, `equal_lengths(['A', 'B'], ['D', 'E'])`, `equal_lengths(['B', 'C'], ['E', 'F'])`, `equal_lengths(['A', 'C'], ['D', 'F'])`, `label_present(A)`, `label_present(D)`

**geo-m1-t4-l3-overlapping-triangles-reflexive-1** `reflexive-property, overlapping-triangles, SAS, shared-side`

> Draw two overlapping triangles that share a common side. Make a quadrilateral ABCD where A is top-left, B is top-right, C is bottom-right, D is bottom-left. Draw diagonal BD to create triangles ABD and CBD. Mark AB = CB with one tick mark each (so B is the top vertex equidistant from A and C). Mark angle ABD = angle CBD with one arc each — so BD bisects angle ABC. The shared side BD should be marked with a special double tick or labeled as 'BD = BD' to show the reflexive property. This sets up SAS congruence for triangles ABD and CBD.

Labels: A, B, C, D
Properties: `equal_lengths(['A', 'B'], ['C', 'B'])`, `equal_lengths(['B', 'D'], ['B', 'D'])`, `angle_equal(['A', 'B', 'D'], ['C', 'B', 'D'])`, `angle_bisector(D, B, A, C)`, `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`

**geo-m2-t1-l3-a5-inscribed-octagon-1** `circle, regular-octagon, inscribed-polygon, angle-bisector, perpendicular-diameters`

> Draw a circle with center O. First draw two perpendicular diameters: A to E (horizontal) and C to G (vertical). These give us four points on the circle at 90-degree spacing. Now bisect each of the four central right angles to get four more points on the circle: B (between A and C), D (between C and E), F (between E and G), and H (between G and A). Connect all eight points in order A, B, C, D, E, F, G, H back to A to form a regular octagon inscribed in the circle. Mark all eight sides as equal and draw all eight radii from O to each vertex.

Labels: O, A, B, C, D, E, F, G, H
Properties: `point_on_circle(A, O, E)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_circle(E, O, A)`, `point_on_circle(F, O, A)`, `point_on_circle(G, O, A)`, `point_on_circle(H, O, A)`, `perpendicular(['A', 'E'], ['C', 'G'])`, `equal_lengths(['A', 'B'], ['B', 'C'], ['C', 'D'], ['D', 'E'], ['E', 'F'], ['F', 'G'], ['G', 'H'], ['H', 'A'])`, `angle_bisector(B, O, A, C)`

**geo-m2-t1-l5-a1-circumcenter-acute-triangle-1** `triangle, circumcenter, perpendicular-bisector, circumscribed-circle`

> Draw an acute triangle ABC. Construct the perpendicular bisector of each side: the perpendicular bisector of AB (mark the midpoint as D), the perpendicular bisector of BC (mark the midpoint as E), and the perpendicular bisector of CA (mark the midpoint as F). All three perpendicular bisectors should meet at a single point — label that point P (the circumcenter). Then draw a circle centered at P that passes through A, B, and C. Mark the right angles at D, E, and F, and show with equal tick marks that PA = PB = PC (the circumradius). The circumcenter P should be inside the triangle.

Labels: A, B, C, D, E, F, P
Properties: `midpoint(D, A, B)`, `midpoint(E, B, C)`, `midpoint(F, C, A)`, `perpendicular(['A', 'B'], ['P', 'D'])`, `perpendicular(['B', 'C'], ['P', 'E'])`, `perpendicular(['C', 'A'], ['P', 'F'])`, `right_angle(A, D, P)`, `right_angle(B, E, P)`, `right_angle(C, F, P)`, `equal_lengths(['P', 'A'], ['P', 'B'], ['P', 'C'])`, `point_on_circle(A, P, B)`, `point_on_circle(B, P, A)`, `point_on_circle(C, P, A)`

**geo-m2-t1-l5-a2-incenter-triangle-1** `triangle, incenter, angle-bisector, inscribed-circle`

> Draw an acute triangle ABC. Construct the angle bisector of each interior angle: bisect angle A (the bisector ray from A goes toward BC), bisect angle B (the ray from B goes toward AC), and bisect angle C (the ray from C goes toward AB). All three angle bisectors meet at a single point inside the triangle — label it I (the incenter). From I, drop perpendicular segments to each side and mark the three equal distances: ID perpendicular to BC, IE perpendicular to AC, IF perpendicular to AB, where D, E, F are the feet of the perpendiculars. Show ID = IE = IF with tick marks and draw the inscribed circle centered at I with radius ID.

Labels: A, B, C, I, D, E, F
Properties: `angle_bisector(I, A, B, C)`, `angle_bisector(I, B, A, C)`, `angle_bisector(I, C, A, B)`, `perpendicular(['I', 'D'], ['B', 'C'])`, `perpendicular(['I', 'E'], ['A', 'C'])`, `perpendicular(['I', 'F'], ['A', 'B'])`, `right_angle(I, D, B)`, `right_angle(I, E, A)`, `right_angle(I, F, A)`, `equal_lengths(['I', 'D'], ['I', 'E'], ['I', 'F'])`, `equidistant_from_sides(I, A, B, C)`

**geo-m2-t1-l5-a3-centroid-triangle-1** `triangle, centroid, median, midpoint, ratio`

> Draw an acute triangle ABC. Find the midpoint of each side and label them: D is the midpoint of BC, E is the midpoint of AC, and F is the midpoint of AB. Draw all three medians: AD (from vertex A to midpoint D), BE (from vertex B to midpoint E), and CF (from vertex C to midpoint F). All three medians meet at one point — label it G (the centroid). Mark the midpoints D, E, F with tick marks. Also mark that AG = 2·GD (the centroid divides each median in a 2:1 ratio from vertex to midpoint) — you can do this by putting a single tick on GD and double tick on AG.

Labels: A, B, C, D, E, F, G
Properties: `midpoint(D, B, C)`, `midpoint(E, A, C)`, `midpoint(F, A, B)`, `point_on_segment(G, A, D)`, `point_on_segment(G, B, E)`, `point_on_segment(G, C, F)`, `centroid(G, A, B, C)`, `mark_present(midpoint, D)`, `mark_present(midpoint, E)`, `mark_present(midpoint, F)`

**geo-m2-t1-l5-a4-orthocenter-acute-triangle-1** `triangle, orthocenter, altitude, perpendicular`

> Draw an acute triangle ABC. Construct all three altitudes: the altitude from A perpendicular to BC (foot of altitude is point D on BC), the altitude from B perpendicular to AC (foot is point E on AC), and the altitude from C perpendicular to AB (foot is point F on AB). All three altitudes should meet inside the triangle at a single point — label it H (the orthocenter). Mark the right angles at D, E, and F where each altitude meets the opposite side. Label all 7 points: A, B, C, D, E, F, H.

Labels: A, B, C, D, E, F, H
Properties: `perpendicular(['A', 'D'], ['B', 'C'])`, `perpendicular(['B', 'E'], ['A', 'C'])`, `perpendicular(['C', 'F'], ['A', 'B'])`, `point_on_segment(D, B, C)`, `point_on_segment(E, A, C)`, `point_on_segment(F, A, B)`, `right_angle(A, D, B)`, `right_angle(B, E, A)`, `right_angle(C, F, A)`, `point_on_segment(H, A, D)`, `point_on_segment(H, B, E)`

**geo-m2-t1-l5-a4-orthocenter-obtuse-triangle-2** `triangle, orthocenter, altitude, perpendicular, obtuse-triangle, exterior`

> Draw an obtuse triangle ABC where angle B is the obtuse angle (greater than 90 degrees). Construct all three altitudes, but notice that for an obtuse triangle, two of the altitudes fall OUTSIDE the triangle. Draw the altitude from A perpendicular to line BC — the foot D will be outside segment BC, past vertex C. Draw the altitude from C perpendicular to line AB — the foot F will be outside segment AB, past vertex B. Draw the altitude from B to AC — foot E is on AC inside the triangle. All three altitude lines meet outside the triangle at point H (the orthocenter). Mark all three right angles at D, E, F and label all 7 points.

Labels: A, B, C, D, E, F, H
Properties: `perpendicular(['A', 'D'], ['B', 'C'])`, `perpendicular(['B', 'E'], ['A', 'C'])`, `perpendicular(['C', 'F'], ['A', 'B'])`, `point_on_segment(E, A, C)`, `right_angle(A, D, C)`, `right_angle(B, E, A)`, `right_angle(C, F, B)`, `point_on_line(D, B, C)`, `point_on_line(F, A, B)`

**geo-m2-t2-l1-tt-central-vertical-angles-circle-1** `circle, central-angles, vertical-angles, paragraph-proof`

> Draw a circle with center O. Draw two diameters that cross at O — one going from point A to point C and the other from point B to point D. Label the four arcs: arc AB, arc BC, arc CD, arc DA. Mark the central vertical angle pairs: arc marks on arc AB and arc CD to show they're equal, and different arc marks on arc BC and arc DA to show they're equal. I'm proving that vertical central angles intercept congruent arcs.

Labels: O, A, B, C, D
Properties: `collinear(A, O, C)`, `collinear(B, O, D)`, `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `angle_equal(['A', 'O', 'B'], ['C', 'O', 'D'])`

**geo-m2-t2-l3-tt-star-exterior-angles-1** `exterior-angles, star-polygon, triangle-sum`

> Draw a triangle with vertices A, B, C. Extend all three sides beyond each vertex to form a six-pointed star shape, creating points P (from extending sides at A), Q (from extending sides at B), and R (from extending sides at C). Label the five starred tip angles. I want to find the sum of those tip angles using the exterior angle theorem and triangle sum theorem.

Labels: A, B, C, P, Q, R
Properties: `collinear(P, A, B)`, `collinear(Q, B, C)`, `collinear(R, C, A)`

**geo-m2-t2-l6-a64-exterior-angle-secant-tangent-1** `exterior-angles-circle, secant, tangent, external-point`

> Draw three separate circles showing the three cases of exterior angles of a circle. Circle 1: external point E with a secant through points A and B (farther and closer on the circle) and a tangent touching at point T. Label arc AT as the far arc and arc BT as the near arc. Label the exterior angle at E. Circle 2: external point E with two secants hitting the circle at A, B (one secant) and C, D (other secant). Circle 3: external point E with two tangents touching at points T1 and T2. Label the intercepted arcs in each case.

Labels: E, A, B, T
Properties: `point_on_circle(T, O, A)`, `point_on_circle(A, O, T)`, `point_on_circle(B, O, T)`, `tangent(['E', 'T'], O, T)`

**geo-m2-t2-l6-a66-mixed-circle-theorems-1** `circle, inscribed-angle, interior-angle, exterior-angle, arc-measures`

> Draw a circle with several features: two chords intersecting inside at point P (endpoints A, B and C, D on the circle), an inscribed angle at point E on the circle intercepting arc FG, and an external point H with two secants hitting the circle at points I, J and K, L. Label specific arc measures: arc AB = 100°, arc CD = 40°, arc FG = 72°, arc IJ = 120°, arc KL = 50°. Ask me to find the interior angle at P, the inscribed angle at E, and the exterior angle at H.

Labels: P, A, B, C, D, E, F, G, H
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `point_on_circle(E, O, A)`, `point_on_segment(P, A, B)`

**geo-m2-t2-l6-tt-inscribed-quad-exterior-angle-1** `inscribed-quadrilateral, exterior-angle, arc-measures, circle-theorems`

> Draw a circle with inscribed quadrilateral ABCD where all four vertices lie on the circle. Extend side AB beyond vertex B to an external point E, forming exterior angle CBE. Label arc CD with a specific measure, say 110°. I want to see why the exterior angle CBE equals the opposite interior angle D (which is angle ADC). Label angle ADC and angle CBE and mark them as equal with matching arcs. One arc measure is given somewhere on the diagram so I can verify the calculation.

Labels: A, B, C, D, E
Properties: `point_on_circle(A, O, B)`, `point_on_circle(B, O, A)`, `point_on_circle(C, O, A)`, `point_on_circle(D, O, A)`, `collinear(A, B, E)`, `angle_equal(['C', 'B', 'E'], ['A', 'D', 'C'])`

**geo-m2-t3-l2-talk-broken-plate-two-chords-1** `circle, chord, perpendicular-bisector, center, diameter, real-world`

> Draw the situation for finding the center of a broken circular plate. Show a partial circle (the fragment — maybe just the top arc). Inside the fragment, draw two chords: chord PQ and chord RS, where P, Q, R, S are all on the arc. Draw the perpendicular bisector of PQ and mark its midpoint as M. Draw the perpendicular bisector of RS and mark its midpoint as N. Label the point where the two perpendicular bisectors intersect as O — this is the center of the full circle. Draw the full circle with center O in a dashed line so I can see the original plate. Mark the right angles at M and N with squares, and mark OM as the radius. Label all points P, Q, R, S, M, N, and O.

Labels: P, Q, R, S, M, N, O
Properties: `midpoint(M, P, Q)`, `midpoint(N, R, S)`, `perpendicular(['P', 'Q'], ['O', 'M'])`, `perpendicular(['R', 'S'], ['O', 'N'])`, `right_angle(P, M, O)`, `right_angle(R, N, O)`, `mark_present(right_angle, M)`, `mark_present(right_angle, N)`, `point_on_line(O, M, P)`, `point_on_line(O, N, R)`

**geo-m2-t3-l3-a3-trapezoid-midsegment-1** `trapezoid, midsegment, midpoint, parallel, triangle-midsegment, proof`

> Draw trapezoid MDSG where M is top-left, D is top-right, S is bottom-right, and G is bottom-left. Mark MD as the top base and GS as the bottom base, with arrows showing MD is parallel to GS. Now find the midpoints of the two legs: let J be the midpoint of leg MG and let E be the midpoint of leg DS. Draw the midsegment JE connecting those two midpoints and mark it as parallel to both bases with arrows. Mark J as the midpoint of MG with tick marks, and mark E as the midpoint of DS with tick marks. Also draw an auxiliary point T by extending side MD and drawing a diagonal from G through D to hit the extension at T — this creates the triangle used in the triangle midsegment theorem proof. Label all points M, D, S, G, J, E, and T.

Labels: M, D, S, G, J, E, T
Properties: `parallel(['M', 'D'], ['G', 'S'])`, `parallel(['J', 'E'], ['M', 'D'])`, `parallel(['J', 'E'], ['G', 'S'])`, `midpoint(J, M, G)`, `midpoint(E, D, S)`, `point_on_segment(D, M, T)`

**geo-m3-t1-l3-act32-angle-bisector-proportional-theorem-1** `angle-bisector, proportional-sides, auxiliary-line, proof`

> Draw triangle ABC where the angle bisector from vertex A meets side BC at point D. Label the sides: AB = 6, AC = 9, BD = 4, and DC = 6 to show that BD/DC = AB/AC. Then add an auxiliary line through vertex C parallel to the angle bisector AD, and extend side BA until it hits that auxiliary line at a new point E. Label point E and show that this creates an isosceles triangle so I can see how the proof of the angle bisector theorem works.

Labels: A, B, C, D, E
Properties: `angle_bisector(D, A, B, C)`, `point_on_segment(D, B, C)`, `parallel(['A', 'D'], ['C', 'E'])`, `collinear(B, A, E)`, `label_present(D)`, `label_present(E)`

**geo-m3-t1-l3-act37-centroid-medians-1** `centroid, medians, concurrency, coordinate-plane`

> Draw triangle ABC on a coordinate plane with A at (0, 6), B at (-4, 0), and C at (4, 0). Find the midpoints of each side and label them: M1 is the midpoint of BC, M2 is the midpoint of AC, and M3 is the midpoint of AB. Draw all three medians from each vertex to the opposite midpoint and label the point where they all meet as G (the centroid). Mark G clearly and label its coordinates.

Labels: A, B, C, M1, M2, M3, G
Properties: `midpoint(M1, B, C)`, `midpoint(M2, A, C)`, `midpoint(M3, A, B)`, `centroid(G, A, B, C)`, `point_on_segment(G, A, M1)`, `point_on_segment(G, B, M2)`, `point_on_segment(G, C, M3)`, `label_present(G)`

**geo-m3-t1-l4-act43-pythagorean-proof-similar-triangles-1** `pythagorean-theorem, similar-triangles, altitude, proof`

> Draw right triangle ABC where the right angle is at C. The hypotenuse is AB. Drop an altitude from C perpendicular to AB and call the foot D. Label the whole hypotenuse AB = c, leg AC = b, leg BC = a. Label the sub-segment AD = x and sub-segment DB = y. I need to see the proportions b/c = x/b and a/c = y/a written next to the diagram so I can follow the Pythagorean theorem proof. Mark the right angle at C and at D.

Labels: A, B, C, D
Properties: `right_angle(A, C, B)`, `right_angle(A, D, C)`, `point_on_segment(D, A, B)`, `perpendicular(['C', 'D'], ['A', 'B'])`, `collinear(A, D, B)`, `mark_present(right_angle, C)`, `mark_present(right_angle, D)`

**geo-m3-t1-l4-gs-altitude-hypotenuse-three-triangles-1** `right-triangle, altitude, hypotenuse, similar-triangles, AA-similarity`

> Draw a right triangle ABC where the right angle is at C, and then draw the altitude from C down to the hypotenuse AB, hitting it at point D. Label all four points: A, B, C, and D. Mark the right angle at C with a square. Also mark the right angle where the altitude meets AB at D. Now I need to see all three similar triangles: the big one (ABC), the left one (ACD), and the right one (CBD). Can you shade or outline each one differently so I can see all three? Label the right angles in each smaller triangle too.

Labels: A, B, C, D
Properties: `right_angle(A, C, B)`, `right_angle(A, D, C)`, `right_angle(C, D, B)`, `point_on_segment(D, A, B)`, `perpendicular(['C', 'D'], ['A', 'B'])`, `label_present(D)`, `mark_present(right_angle, C)`, `mark_present(right_angle, D)`

**geo-m3-t1-l6-act63-partition-triangle-proportionality-coordinate-1** `directed-line-segment, triangle-proportionality, coordinate-plane, parallel-lines, partition`

> Draw a coordinate plane with directed segment from A at (0, 0) to B at (6, 9). Add an auxiliary point C at (6, 0) to form right triangle ABC. I want to divide the segment AC (the horizontal leg) into three equal parts and draw lines parallel to BC through those division points, hitting AB at partition points. Label the division points on AC as D1 at (2, 0) and D2 at (4, 0). Draw lines through D1 and D2 parallel to BC and label where they intersect AB as P1 and P2. The point P1 should partition AB in a 1:2 ratio. Label P1 with its coordinates.

Labels: A, B, C, D1, D2, P1, P2
Properties: `right_angle(A, C, B)`, `point_on_segment(D1, A, C)`, `point_on_segment(D2, A, C)`, `parallel(['D1', 'P1'], ['B', 'C'])`, `parallel(['D2', 'P2'], ['B', 'C'])`, `point_on_segment(P1, A, B)`, `point_on_segment(P2, A, B)`, `equal_lengths(['A', 'D1'], ['D1', 'D2'])`, `equal_lengths(['D1', 'D2'], ['D2', 'C'])`

**geo-m4-t1-l3-act33-dog-park-sectors-1** `circles, sectors, composite-area, real-world`

> Draw a dog park layout where a dog is tied to a post at point P. The dog can roam in two different sectors: one sector has radius 2 ft and central angle 90°, and an adjacent sector has radius 10 ft with the same 90° central angle, opening in the opposite direction. Label P as the post, label the two radii (2 ft and 10 ft), mark both 90° central angles, and shade both sector regions so I can find the total area the dog can reach.

Labels: P
Properties: `label_present(P)`

**geo-m4-t1-l5-talktalk-point-on-circle-perpendicular-1** `circles, coordinate-geometry, points-on-circle, pythagorean-theorem, perpendicular-radius`

> Draw a coordinate plane with a circle centered at point O = (6, −5) with radius 10. Draw two perpendicular radii OA and OB — let OA go straight up to A = (6, 5). Then I know there's a point C on the circle whose x-coordinate is 12. Draw a vertical dashed line at x = 12 that intersects the circle at point C. Draw the right triangle from O to a point D = (12, −5) directly to the right of O, and then up to C. Label O, A, B, C, D, mark the right angle at D, and show the legs OD = 6 and DC = 8 so I can verify OC = 10.

Labels: O, A, B, C, D
Properties: `right_angle(O, D, C)`, `perpendicular(['O', 'A'], ['O', 'B'])`, `point_on_circle(C, O, A)`, `point_on_circle(A, O, A)`, `equal_lengths(['O', 'A'], ['O', 'C'])`, `label_present(O)`, `label_present(A)`, `label_present(C)`, `label_present(D)`, `collinear(O, D, B)`

**geo-m4-t2-l2-a22-cube-cross-sections-1** `cross-section, cube, polygon, plane`

> Draw four separate diagrams of a cube ABCDEFGH where ABCD is the bottom face and EFGH is the top face (E above A, F above B, G above C, H above D). In the first cube, show a cross-section parallel to the base that gives a square — label it. In the second cube, show a diagonal cross-section connecting midpoints of edges that forms a rectangle. In the third cube, show a cross-section cutting three faces that forms a triangle — mark where the plane hits the three edges. In the fourth cube, show a cross-section cutting through six faces to form a hexagon. Label all vertices on each cube and shade each cross-section differently.

Labels: A, B, C, D, E, F, G, H
Properties: `label_present(A)`, `label_present(B)`, `label_present(C)`, `label_present(D)`, `label_present(E)`, `label_present(F)`, `label_present(G)`, `label_present(H)`, `parallel(['A', 'B'], ['E', 'F'])`, `equal_lengths(['A', 'B'], ['B', 'C'], ['A', 'E'])`

**geo-m4-t2-l3-a34-composite-solids-1** `composite-solids, pyramid, prism, hemisphere, cone, volume`

> Draw two composite solids. First: a rectangular prism with length 8, width 6, and height 4 as the base, topped by a square pyramid with the same 8×6 base and a height of 3 — label all dimensions and mark the boundary between the two solids with a dashed line. Second: a hemisphere sitting flat-side down with radius 5, with a cone sitting on top of it (cone's base matches the hemisphere's flat circle, radius 5, cone height 7) — label all dimensions and mark the flat circle boundary between hemisphere and cone. Show these side by side.

Labels: r, h
Properties: `label_present(r)`, `label_present(h)`, `equal_lengths(['A', 'B'], ['P', 'Q'])`, `equal_lengths(['O', 'R1'], ['O', 'R2'])`

**geo-m4-t2-l4-a43-composite-surface-area-1** `composite-solids, surface-area, hemisphere, cone, cylinder`

> Draw a composite solid made of a hemisphere on the bottom (flat side up, radius r = 4), a cylinder in the middle (same radius r = 4, height h = 6), and a cone on top (same radius r = 4, slant height s = 5). Label all dimensions: r = 4 on each piece, h = 6 on the cylinder, s = 5 on the cone. Draw dashed lines at the junctions between pieces to show where they connect. Mark with X's or shading the two circular faces where the pieces join (top of hemisphere = bottom of cylinder, and top of cylinder = bottom of cone) to show those interior faces are NOT included in surface area. Label visible surfaces.

Labels: r, h, s
Properties: `label_present(r)`, `label_present(h)`, `label_present(s)`, `equal_lengths(['O1', 'R1'], ['O2', 'R2'], ['O3', 'R3'])`, `perpendicular(['top_center', 'bottom_center'], ['left_edge', 'right_edge'])`
