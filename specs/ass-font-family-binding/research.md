# Research — ASS font-family binding

Parent: `specs/true-10-10-acceptance/plan.md`, Phase 8.

Serena is unavailable; `rg` mapped the font checks, ASS construction, render caller, tests, and
D-133 evidence.

`render_clip` calls `assert_fonts_dir_covers_kurdish(fonts_dir)`, which accepts when any font file
in the directory covers the required Kurdish glyphs. The ASS is read separately and its `Fontname`
is never related to the accepted file. A covering unrelated font can therefore certify a subtitle
file that asks libass for a missing or non-covering family. A hand-written `\\fn` override can also
replace the style family after the check.

The shipped `NotoNaskhArabic-Regular.ttf` has name-table ID 1 `Noto Naskh Arabic`, ID 2 `Regular`,
ID 4 `Noto Naskh Arabic Regular`, and ID 6 `NotoNaskhArabic-Regular`. `build_ass` asks for the ID 1
family exactly. D-133 explicitly names this missing family binding as the remaining M3.3 shortfall.

The production chokepoint is the burn, not only `build_ass`: `render_clip` accepts externally
supplied ASS files. A correct guard must parse the style actually used by Dialogue events, bind its
family to the name table of a font inside the supplied directory, check that same font's Kurdish
coverage, and refuse inline font-family overrides rather than pretending to emulate libass/fontconfig
fallback rules.
