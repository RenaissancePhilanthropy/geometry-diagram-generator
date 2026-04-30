PAPER = geogen
LATEXMK = latexmk

.PHONY: all watch clean view help

all: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex preamble.tex abstract.tex refs.bib \
              sections/*.tex appendices/*.tex \
              figures/*
	$(LATEXMK) -lualatex -interaction=nonstopmode -halt-on-error -synctex=1 $(PAPER).tex

watch:
	$(LATEXMK) -lualatex -pvc -interaction=nonstopmode -synctex=1 $(PAPER).tex

view: $(PAPER).pdf
	open $(PAPER).pdf

clean:
	$(LATEXMK) -C
	rm -f *.bbl *.blg *.aux *.log *.out *.fls *.fdb_latexmk *.synctex.gz *.toc *.nav *.snm
	rm -f sections/*.aux appendices/*.aux

help:
	@echo "make         - build $(PAPER).pdf"
	@echo "make watch   - continuous rebuild on save (latexmk -pvc)"
	@echo "make view    - open the PDF"
	@echo "make clean   - remove build artefacts"
