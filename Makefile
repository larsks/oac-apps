# use https://github.com/kitproj/junit2html to generate
# HTML output from chainsaw-report.xml.
all: chainsaw-report.html

chainsaw-report.html: chainsaw-report-fixed.xml
	junit2html < $< > $@ || { rm -f $@; exit 1; }

chainsaw-report-fixed.xml: chainsaw-report.xml
	xsltproc docs/chainsaw-fixup.xsl $< > $@ || { rm -f $@; exit 1; }

clean:
	rm -f chainsaw-report.html chainsaw-report-fixed.xml
