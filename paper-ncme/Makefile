PAPER = main
LATEXMK = latexmk

.PHONY: all watch clean view help

all: $(PAPER).pdf

# ACL recommends pdfLaTeX. acl_natbib is a BibTeX style (latexmk runs bibtex).
$(PAPER).pdf: $(PAPER).tex preamble.tex abstract.tex acl.sty acl_natbib.bst refs.bib sections/*.tex
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -synctex=1 $(PAPER).tex

watch:
	$(LATEXMK) -pdf -pvc -interaction=nonstopmode -synctex=1 $(PAPER).tex

view: $(PAPER).pdf
	open $(PAPER).pdf

clean:
	$(LATEXMK) -C
	rm -f *.bbl *.blg *.aux *.log *.out *.fls *.fdb_latexmk *.synctex.gz
	rm -f sections/*.aux

help:
	@echo "make       - build $(PAPER).pdf with pdflatex"
	@echo "make watch - continuous rebuild on save"
	@echo "make clean - remove build artefacts"
