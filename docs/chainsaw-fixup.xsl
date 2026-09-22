<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" indent="yes"/>

  <!-- identity transform: copy everything unchanged unless overridden below -->
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- classname is always empty in chainsaw's output, which makes junit2html
       group every test under "no-testclass"; use the enclosing testsuite's
       name (the test path) instead -->
  <xsl:template match="testcase/@classname">
    <xsl:attribute name="classname">
      <xsl:value-of select="../../@name"/>
    </xsl:attribute>
  </xsl:template>

  <!-- chainsaw puts the whole error in the message attribute and leaves the
       element body empty, so junit2html's <pre> block just shows "failed";
       move the message into the element text so it renders preformatted.
       message is kept as an empty attribute because junit2html renders a
       missing one as the string "None" -->
  <xsl:template match="failure|error">
    <xsl:copy>
      <xsl:apply-templates select="@*[name() != 'message']"/>
      <xsl:attribute name="message"/>
      <xsl:value-of select="@message"/>
    </xsl:copy>
  </xsl:template>
</xsl:stylesheet>
