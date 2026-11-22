"""Hermetic tests for the erp-xpp metadata lookup helper (no SDK needed)."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import textwrap
import unittest
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[1] / "plugins" / "dataverse"
    / "skills" / "erp-xpp" / "scripts" / "xpp_lookup.py"
)
spec = importlib.util.spec_from_file_location("erp_xpp_lookup", SCRIPT)
lookup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lookup)

TABLE = """\
<?xml version="1.0" encoding="utf-8"?>
<AxTable xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>ContosoLine</Name>
  <SourceCode>
    <Declaration><![CDATA[
using Contoso.Instrumentation;
public class ContosoLine extends common
{
}
]]></Declaration>
    <Methods>
      <Method>
        <Name>validateWrite</Name>
        <Source><![CDATA[
    /// <summary>Validates the line.</summary>
    public boolean  validateWrite(boolean _skipCheck = false, str _note = strFmt("%1,%2", 1, 2))
    {
        return true;
    }
]]></Source>
      </Method>
      <Method>
        <Name>helper</Name>
        <Source><![CDATA[
    private void helper()
    {
    }
]]></Source>
      </Method>
      <Method>
        <Name>locked</Name>
        <Source><![CDATA[
    [Hookable(false)]
    public void locked()
    {
    }
]]></Source>
      </Method>
      <Method>
        <Name>sealedOne</Name>
        <Source><![CDATA[
    final public void sealedOne()
    {
    }
]]></Source>
      </Method>
    </Methods>
  </SourceCode>
  <Fields>
    <AxTableField xmlns="" i:type="AxTableFieldString">
      <Name>LineRef</Name>
      <ExtendedDataType>ContosoLineRef</ExtendedDataType>
      <Mandatory>Yes</Mandatory>
    </AxTableField>
    <AxTableField xmlns="" i:type="AxTableFieldReal">
      <Name>Qty</Name>
      <ExtendedDataType>Qty</ExtendedDataType>
    </AxTableField>
  </Fields>
  <FieldGroups>
    <AxTableFieldGroup>
      <Name>Reference</Name>
      <Fields>
        <AxTableFieldGroupField>
          <DataField>LineRef</DataField>
        </AxTableFieldGroupField>
      </Fields>
    </AxTableFieldGroup>
  </FieldGroups>
  <Indexes>
    <AxTableIndex>
      <Name>LineRefIdx</Name>
    </AxTableIndex>
  </Indexes>
</AxTable>
"""

FORM = """\
<?xml version="1.0" encoding="utf-8"?>
<AxForm xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns="Microsoft.Dynamics.AX.Metadata.V6">
  <Name>ContosoOrder</Name>
  <SourceCode>
    <Methods xmlns="">
      <Method>
        <Name>init</Name>
        <Source><![CDATA[
    public void init()
    {
        super();
    }
]]></Source>
      </Method>
    </Methods>
    <DataSources xmlns="">
      <DataSource>
        <Name>ContosoLine</Name>
        <Methods>
          <Method>
            <Name>active</Name>
            <Source><![CDATA[
        int active(boolean _partOnly = false)
        {
            return super();
        }
]]></Source>
          </Method>
        </Methods>
      </DataSource>
    </DataSources>
  </SourceCode>
  <DataSources>
    <AxFormDataSource xmlns="">
      <Name>ContosoHeader</Name>
      <Table>ContosoHeader</Table>
    </AxFormDataSource>
    <AxFormDataSource xmlns="">
      <Name>ContosoLine</Name>
      <Table>ContosoLine</Table>
      <JoinSource>ContosoHeader</JoinSource>
    </AxFormDataSource>
  </DataSources>
  <Design>
    <Pattern xmlns="">DetailsTransaction</Pattern>
    <PatternVersion xmlns="">1.4</PatternVersion>
    <Controls xmlns="">
      <AxFormControl xmlns="" i:type="AxFormTabControl">
        <Name>MainTab</Name>
        <Controls>
          <AxFormControl xmlns="" i:type="AxFormTabPageControl">
            <Name>LinesPage</Name>
            <Pattern>FieldsFieldGroups</Pattern>
            <Controls>
              <AxFormControl xmlns="" i:type="AxFormGridControl">
                <Name>LineGrid</Name>
                <DataSource>ContosoLine</DataSource>
                <Controls>
                  <AxFormControl xmlns="" i:type="AxFormStringControl">
                    <Name>LineGrid_LineRef</Name>
                    <DataSource>ContosoLine</DataSource>
                    <DataField>LineRef</DataField>
                  </AxFormControl>
                </Controls>
              </AxFormControl>
            </Controls>
          </AxFormControl>
        </Controls>
      </AxFormControl>
    </Controls>
  </Design>
</AxForm>
"""

CLASS_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<AxClass xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>{name}</Name>
  <SourceCode>
    <Declaration><![CDATA[
{declaration}
]]></Declaration>
    <Methods />
  </SourceCode>
</AxClass>
"""


def write(root, relative, text):
    path = Path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = lookup.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sdk = self.tmp.name
        app = "ContosoSuite/Foundation"
        write(self.sdk, f"{app}/AxTable/ContosoLine.xml", TABLE)
        write(self.sdk, f"{app}/AxForm/ContosoOrder.xml", FORM)
        write(self.sdk, "ContosoRetail/ContosoRetail/AxFormExtension/ContosoOrder.ContosoRetail.xml", "<AxFormExtension />")
        write(self.sdk, "ContosoRetail/ContosoRetail/AxTableExtension/ContosoLine.ContosoRetail.xml", "<AxTableExtension />")
        classes = {
            "ContosoOrderForm_Extension": "[ExtensionOf(formStr(ContosoOrder))]\nfinal class ContosoOrderForm_Extension\n{\n}",
            "ContosoOrderLineDs_Extension":
                "[ExtensionOf(formDataSourceStr(ContosoOrder, ContosoLine))]\nfinal class ContosoOrderLineDs_Extension\n{\n}",
            "ContosoOrderTable_Extension": "[ExtensionOf(tableStr(ContosoOrder))]\nfinal class ContosoOrderTable_Extension\n{\n}",
            "RetailHandlers":
                "class RetailHandlers\n{\n    [FormControlEventHandler(formControlStr(ContosoOrder, LineGrid), FormControlEventType::Clicked)]\n"
                "    public static void onClicked(FormControl _sender, FormControlEventArgs _e) {}\n}",
        }
        for name, declaration in classes.items():
            write(self.sdk, f"ContosoRetail/ContosoRetail/AxClass/{name}.xml",
                  CLASS_TEMPLATE.format(name=name, declaration=declaration))

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_reports_package_and_model(self):
        code, out, _ = run("find", "table", "ContosoLine", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("table ContosoLine: ContosoSuite/Foundation", out)

    def test_find_unknown_name_suggests_similar(self):
        code, out, _ = run("find", "table", "Line", "--sdk", self.sdk)
        self.assertEqual(code, 1)
        self.assertIn("No table named Line.", out)
        self.assertIn("ContosoLine", out)

    def test_member_with_defaults_gets_wrapper_signature(self):
        code, out, _ = run("members", "table", "ContosoLine", "--member", "validateWrite", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn('public boolean validateWrite(boolean _skipCheck = false, str _note = strFmt("%1,%2", 1, 2))', out)
        self.assertIn("wrapper: public boolean validateWrite(boolean _skipCheck, str _note)", out)
        self.assertIn("public class ContosoLine extends common", out)
        self.assertNotIn("using Contoso", out)

    def test_members_that_cannot_be_wrapped_say_why(self):
        for member, note in (("helper", "private: cannot be wrapped"),
                             ("locked", "Hookable(false)"),
                             ("sealedOne", "final: cannot be wrapped unless marked [Wrappable(true)]")):
            code, out, _ = run("members", "table", "ContosoLine", "--member", member, "--sdk", self.sdk)
            self.assertEqual(code, 0)
            self.assertIn(note, out)
            self.assertNotIn("wrapper:", out)

    def test_unknown_member_lists_the_real_ones(self):
        code, out, _ = run("members", "table", "ContosoLine", "--member", "validateWrites", "--sdk", self.sdk)
        self.assertEqual(code, 1)
        self.assertIn("No method validateWrites here.", out)
        self.assertIn("validateWrite", out)

    def test_form_data_source_member(self):
        code, out, _ = run("members", "form", "ContosoOrder", "--datasource", "ContosoLine", "--member", "active",
                           "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("int active(boolean _partOnly = false)", out)
        self.assertIn("wrapper: int active(boolean _partOnly)", out)

    def test_form_control_search_gives_parent_and_pattern_container(self):
        code, out, _ = run("form", "ContosoOrder", "--control", "LineGrid", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("pattern: DetailsTransaction 1.4", out)
        self.assertIn("LineGrid [Grid DataSource=ContosoLine] parent=LinesPage", out)
        self.assertIn("LineGrid_LineRef [String DataSource=ContosoLine DataField=LineRef] parent=LineGrid "
                      "pattern-container=LinesPage(FieldsFieldGroups)", out)
        self.assertIn("1 form extensions add to this form", out)

    def test_form_parent_lists_direct_children_only(self):
        code, out, _ = run("form", "ContosoOrder", "--parent", "linegrid", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("controls directly under linegrid (1):", out)
        self.assertIn("LineGrid_LineRef [String DataSource=ContosoLine DataField=LineRef] parent=LineGrid", out)
        self.assertNotIn("LineGrid [Grid", out)

    def test_form_summary_lists_data_sources_with_joins(self):
        code, out, _ = run("form", "ContosoOrder", "--depth", "0", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("ContosoHeader, ContosoLine<ContosoHeader", out)
        self.assertIn("MainTab [Tab] parent=Design", out)
        self.assertNotIn("LineGrid", out)

    def test_table_field_filter_shows_type_mandatory_and_groups(self):
        code, out, _ = run("table", "ContosoLine", "--field", "ref", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("LineRef [String ContosoLineRef mandatory] groups: Reference", out)
        self.assertNotIn("Qty", out)
        self.assertIn("1 table extensions add to this table", out)

    def test_extensions_filter_by_kind_and_name(self):
        code, out, _ = run("extensions", "form", "ContosoOrder", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("ContosoOrder.ContosoRetail (ContosoRetail/ContosoRetail)", out)
        self.assertIn("ContosoOrderForm_Extension", out)
        self.assertIn("ExtensionOf formDataSourceStr(ContosoOrder, ContosoLine)", out)
        self.assertNotIn("ContosoOrderTable_Extension", out)  # a table of the same name is not the form
        self.assertNotIn("RetailHandlers", out)  # its file name doesn't contain the target

    def test_extensions_all_scans_every_class(self):
        code, out, _ = run("extensions", "form", "ContosoOrder", "--all", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("RetailHandlers (ContosoRetail/ContosoRetail): FormControlEventHandler "
                      "formControlStr(ContosoOrder, LineGrid)", out)

    def test_output_is_capped(self):
        code, out, _ = run("members", "table", "ContosoLine", "--limit", "2", "--sdk", self.sdk)
        self.assertEqual(code, 0)
        self.assertIn("... 2 more; pass --member <name>", out)

    def test_include_adds_a_source_root(self):
        with tempfile.TemporaryDirectory() as src:
            write(src, "ContosoExt/ContosoExt/AxClass/ContosoLineMy_Extension.xml",
                  CLASS_TEMPLATE.format(name="ContosoLineMy_Extension",
                                        declaration="[ExtensionOf(tableStr(ContosoLine))]\nfinal class ContosoLineMy_Extension\n{\n}"))
            code, out, _ = run("extensions", "table", "ContosoLine", "--sdk", self.sdk, "--include", src)
        self.assertEqual(code, 0)
        self.assertIn("ContosoLineMy_Extension (ContosoExt/ContosoExt): ExtensionOf tableStr(ContosoLine)", out)


def descriptor(name, refs, module=None, publisher="Contoso"):
    references = "".join(f"<d2p1:string>{ref}</d2p1:string>" for ref in refs)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<AxModelInfo xmlns:i="http://www.w3.org/2001/XMLSchema-instance">'
        f"<Layer>8</Layer><ModelModule>{module or name}</ModelModule>"
        '<ModuleReferences xmlns:d2p1="http://schemas.microsoft.com/2003/10/Serialization/Arrays">'
        f"{references}</ModuleReferences><Name>{name}</Name><Publisher>{publisher}</Publisher></AxModelInfo>"
    )


class ModelCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sdk = os.path.join(self.tmp.name, "sdk")
        self.src = os.path.join(self.tmp.name, "src")
        write(self.sdk, "ContosoSuite/Descriptor/Foundation.xml", descriptor("Foundation", [], module="ContosoSuite"))
        write(self.sdk, "ContosoSuite/Foundation/AxTable/ContosoLine.xml", TABLE)
        write(self.sdk, "ContosoPlatform/Descriptor/ContosoPlatform.xml", descriptor("ContosoPlatform", []))
        write(self.sdk, "ContosoPlatform/ContosoPlatform/AxEdt/ContosoLineRef.xml",
              '<AxEdt xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="AxEdtString"><Name>ContosoLineRef</Name></AxEdt>')
        write(self.sdk, "ContosoRetail/Descriptor/ContosoRetail.xml", descriptor("ContosoRetail", []))
        write(self.sdk, "ContosoRetail/ContosoRetail/AxEnum/ContosoChannelModifier.xml", "<AxEnum><Name>ContosoChannelModifier</Name></AxEnum>")
        write(self.src, "FabrikamExt/FabrikamExt/AxTableExtension/ContosoLine.FabrikamExt.xml", """\
            <AxTableExtension xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
              <Name>ContosoLine.FabrikamExt</Name>
              <Fields>
                <AxTableField xmlns="" i:type="AxTableFieldString">
                  <Name>FabrikamRef</Name>
                  <ExtendedDataType>ContosoLineRef</ExtendedDataType>
                </AxTableField>
              </Fields>
            </AxTableExtension>
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def model(self, refs, *extra, **descriptor_args):
        write(self.src, "FabrikamExt/Descriptor/FabrikamExt.xml", descriptor("FabrikamExt", refs, **descriptor_args))
        return run("model", "FabrikamExt", "--sdk", self.sdk, "--include", self.src, *extra)

    def test_complete_references_pass(self):
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)
        self.assertIn("packages its metadata uses directly (2): ContosoPlatform, ContosoSuite", out)
        self.assertIn("result: OK", out)

    def test_missing_reference_names_the_file_that_needs_it(self):
        code, out, _ = self.model(["ContosoSuite"])
        self.assertEqual(code, 1)
        self.assertIn("ContosoPlatform: AxTableExtension/ContosoLine.FabrikamExt uses edt ContosoLineRef", out)

    def test_compile_log_references_and_missing_types(self):
        log = os.path.join(self.tmp.name, "xppc.log")
        Path(log).write_text(
            "Compile Error: Class Method dynamics://Class/X/Method/y: [(1,1),(1,2)]: A reference to "
            "'Dynamics.AX.ContosoPlatform, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null' is required.\n"
            "MetadataProvider Error: View dynamics://View/V: Enum type 'ContosoChannelModifier' for the field "
            "'Modifier' is not found.\n", encoding="utf-8")
        code, out, _ = self.model(["ContosoSuite"], "--compile-log", log)
        self.assertEqual(code, 1)
        self.assertIn("ContosoRetail: compiler: ContosoChannelModifier not found; it is defined in ContosoRetail", out)
        self.assertIn("ContosoPlatform: AxTableExtension/ContosoLine.FabrikamExt", out)  # found from metadata first

    def add_called_types(self):
        """ContosoHeader's members use types from four more packages, each in a different way."""
        for package, folder, name in (("ContosoTax", "AxClass", "ContosoTaxCalc"),
                                      ("ContosoFiscal", "AxEnum", "ContosoFiscalType"),
                                      ("ContosoCase", "AxClass", "ContosoCaseArgs"),
                                      ("ContosoBank", "AxClass", "ContosoBankRate")):
            write(self.sdk, f"{package}/Descriptor/{package}.xml", descriptor(package, []))
            write(self.sdk, f"{package}/{package}/{folder}/{name}.xml", f"<{folder}><Name>{name}</Name></{folder}>")

        def table(name, methods, fields=""):
            body = "".join(f"<Method><Name>m{i}</Name><Source><![CDATA[\n{source}\n{{\n}}\n]]></Source></Method>"
                           for i, source in enumerate(methods))
            write(self.sdk, f"ContosoSuite/Foundation/AxTable/{name}.xml",
                  f'<AxTable xmlns:i="http://www.w3.org/2001/XMLSchema-instance"><Name>{name}</Name>'
                  f"<SourceCode><Methods>{body}</Methods></SourceCode><Fields>{fields}</Fields></AxTable>")

        table("ContosoHeader", [
            "public ContosoChannelModifier modifier()",  # instance: needed when code calls header.x
            "public ContosoPayment payment()",
            "private void rate(ContosoBankRate _rate)",  # private instance members count too
            "public static ContosoTaxCalc taxCalc()",  # static: needed only when the code calls ContosoHeader::taxCalc
            "public static ContosoHeader find(str _id)",
            "[SubscribesTo(classStr(ContosoCaseArgs), delegateStr(ContosoCaseArgs, changed))]\n"
            "public static void onChanged(ContosoCaseArgs _args)",
        ], fields='<AxTableField xmlns="" i:type="AxTableFieldEnum"><Name>Fiscal</Name>'
                  "<EnumType>ContosoFiscalType</EnumType></AxTableField>")  # field types never count
        table("ContosoPayment", ["public ContosoTaxCalc calc()"])

    def code(self, body):
        write(self.src, "FabrikamExt/FabrikamExt/AxClass/ContosoLineFabrikam_Extension.xml", f"""\
            <AxClass xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
              <Name>ContosoLineFabrikam_Extension</Name>
              <SourceCode>
                <Declaration><![CDATA[
            [ExtensionOf(tableStr(ContosoLine))]
            final class ContosoLineFabrikam_Extension
            {{
            }}
            ]]></Declaration>
                <Methods><Method><Name>fabrikamCheck</Name><Source><![CDATA[
            public boolean fabrikamCheck()
            {{
                {body}
            }}
            ]]></Source></Method></Methods>
              </SourceCode>
            </AxClass>
            """)

    def test_instance_calls_predict_the_called_type_s_instance_member_packages(self):
        self.add_called_types()
        self.code("ContosoHeader header;\n    // ContosoTaxCalc in a comment is ignored\n"
                  "    return header.modifier() != 0;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 1)
        self.assertIn("add before compiling: packages the standard types this code calls into need (2):", out)
        self.assertIn("ContosoRetail: ContosoHeader.modifier uses enum ContosoChannelModifier; "
                      "ContosoLineFabrikam_Extension.fabrikamCheck calls ContosoHeader", out)
        self.assertIn("ContosoBank: ContosoHeader.rate uses class ContosoBankRate", out)
        for unused in ("ContosoTax", "ContosoFiscal", "ContosoCase"):
            self.assertNotIn(unused, out)

    def test_call_chains_follow_return_types(self):
        self.add_called_types()
        self.code("ContosoHeader header;\n    return header.payment().calc() != null;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "ContosoRetail", "ContosoBank"])
        self.assertEqual(code, 1)
        self.assertIn("ContosoTax: ContosoPayment.calc uses class ContosoTaxCalc; "
                      "ContosoLineFabrikam_Extension.fabrikamCheck calls ContosoPayment", out)

    def test_a_static_call_needs_only_that_method_s_signature(self):
        self.add_called_types()
        self.code("return ContosoHeader::taxCalc() != null;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 1)
        self.assertIn("ContosoTax: ContosoHeader.taxCalc uses class ContosoTaxCalc; "
                      "ContosoLineFabrikam_Extension.fabrikamCheck calls ContosoHeader::taxCalc", out)
        for unused in ("ContosoRetail", "ContosoBank", "ContosoCase"):
            self.assertNotIn(unused, out)
        self.code("return ContosoHeader::find('H1').RecId != 0;")  # find's signature uses no other package
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)

    def test_reading_a_field_loads_nothing(self):
        self.add_called_types()
        self.code("ContosoHeader header;\n    return header.Fiscal != 0;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)

    def test_already_referenced_packages_are_still_listed(self):
        self.add_called_types()
        self.code("ContosoHeader header;\n    return header.modifier() != 0;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "ContosoRetail", "ContosoBank"])
        self.assertEqual(code, 0, out)
        self.assertIn("packages its code's calls also need (2): ContosoBank, ContosoRetail", out)

    def test_types_the_code_names_are_direct_references(self):
        self.add_called_types()
        self.code("ContosoTaxCalc calc;\n    return calc == null;")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 1)
        self.assertIn("add to ModuleReferences (1):", out)
        self.assertIn("ContosoTax: ContosoLineFabrikam_Extension.fabrikamCheck uses class ContosoTaxCalc", out)
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "ContosoTax"])
        self.assertEqual(code, 0, out)

    def test_extending_a_table_adds_no_references_for_its_members_or_fields(self):
        self.add_called_types()
        write(self.src, "FabrikamExt/FabrikamExt/AxTableExtension/ContosoHeader.FabrikamExt.xml",
              "<AxTableExtension><Name>ContosoHeader.FabrikamExt</Name></AxTableExtension>")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)
        self.assertIn("result: OK", out)

    def test_code_naming_a_form_predicts_the_enums_behind_its_view_fields(self):
        self.add_called_types()
        write(self.sdk, "ContosoSuite/Foundation/AxTable/ContosoChannelGroup.xml", """\
            <AxTable xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
              <Name>ContosoChannelGroup</Name>
              <Fields><AxTableField xmlns="" i:type="AxTableFieldEnum"><Name>Modifier</Name>
                <EnumType>ContosoChannelModifier</EnumType></AxTableField></Fields>
            </AxTable>
            """)
        write(self.sdk, "ContosoSuite/Foundation/AxView/ContosoChannelView.xml", """\
            <AxView xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
              <Name>ContosoChannelView</Name>
              <Fields><AxViewField xmlns="" i:type="AxViewFieldBound"><Name>Modifier</Name>
                <DataField>Modifier</DataField><DataSource>ChannelGroup</DataSource></AxViewField></Fields>
              <ViewMetadata><DataSources><AxQuerySimpleRootDataSource>
                <Name>ChannelGroup</Name><Table>ContosoChannelGroup</Table>
              </AxQuerySimpleRootDataSource></DataSources></ViewMetadata>
            </AxView>
            """)
        write(self.sdk, "ContosoSuite/Foundation/AxForm/ContosoHeaderForm.xml", """\
            <AxForm xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns="Microsoft.Dynamics.AX.Metadata.V6">
              <Name>ContosoHeaderForm</Name>
              <DataSources>
                <AxFormDataSource xmlns=""><Name>Header</Name><Table>ContosoHeader</Table></AxFormDataSource>
                <AxFormDataSource xmlns=""><Name>Channels</Name><Table>ContosoChannelView</Table></AxFormDataSource>
              </DataSources>
              <Design />
            </AxForm>
            """)
        write(self.src, "FabrikamExt/FabrikamExt/AxFormExtension/ContosoHeaderForm.FabrikamExt.xml",
              '<AxFormExtension xmlns="Microsoft.Dynamics.AX.Metadata.V6"><Name>ContosoHeaderForm.FabrikamExt</Name></AxFormExtension>')
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)  # a form extension alone doesn't make the compiler load the form
        write(self.src, "FabrikamExt/FabrikamExt/AxClass/ContosoHeaderFormFabrikam_Extension.xml",
              CLASS_TEMPLATE.format(name="ContosoHeaderFormFabrikam_Extension", declaration=(
                  "[ExtensionOf(formDataSourceStr(ContosoHeaderForm, Header))]\n"
                  "final class ContosoHeaderFormFabrikam_Extension\n{\n}")))
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 1)
        self.assertIn("ContosoRetail: form ContosoHeaderForm data source Channels (a view) field Modifier "
                      "uses enum ContosoChannelModifier; ContosoHeaderFormFabrikam_Extension names the form", out)
        self.assertNotIn("ContosoFiscal", out)  # a table data source's field types don't count
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "ContosoRetail"])
        self.assertEqual(code, 0, out)

    def add_base_model(self, binary=False):
        """FabrikamBase, another model in the repo (or an ISV's binary package), adds ContosoHeader.fabrikamRisk()."""
        shutil.rmtree(os.path.join(self.src, "FabrikamBase"), ignore_errors=True)
        write(self.src, "FabrikamBase/Descriptor/FabrikamBase.xml", descriptor("FabrikamBase", ["ContosoSuite"]))
        if binary:  # what an ISV ships: compiled metadata, no source; builds leave empty Ax* folders behind
            Path(self.src, "FabrikamBase", "FabrikamBase", "AxClass").mkdir(parents=True)
            write(self.src, "FabrikamBase/XppMetadata/FabrikamBase/AxClass/ContosoHeaderFabrikamBase_Extension.xml", """\
                <z:anyType xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="AxCompilerMetadata"
                    xmlns:z="http://schemas.microsoft.com/2003/10/Serialization/">
                  <Attributes><AxAttribute><Name>ExtensionOf</Name><Parameters><AxAttributeParameter>
                    <TypeValue>tableStr</TypeValue>
                    <AdditionalData><AxAttributeParameter><TypeValue>ContosoHeader</TypeValue></AxAttributeParameter></AdditionalData>
                  </AxAttributeParameter></Parameters></AxAttribute></Attributes>
                  <Methods><Method><Name>fabrikamRisk</Name><ReturnType><Type>Class</Type>
                    <TypeName>FabrikamRisk</TypeName></ReturnType></Method></Methods>
                </z:anyType>
                """)
            write(self.src, "FabrikamBase/XppMetadata/FabrikamBase/AxClass/FabrikamRisk.xml", """\
                <z:anyType xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="AxCompilerMetadata"
                    xmlns:z="http://schemas.microsoft.com/2003/10/Serialization/">
                  <Methods><Method><Name>calc</Name><ReturnType><Type>Class</Type>
                    <TypeName>ContosoTaxCalc</TypeName></ReturnType></Method>
                  <Method><Name>make</Name><IsStatic>true</IsStatic><ReturnType><Type>Class</Type>
                    <TypeName>ContosoBankRate</TypeName></ReturnType></Method></Methods>
                </z:anyType>
                """)
            return
        write(self.src, "FabrikamBase/FabrikamBase/AxClass/ContosoHeaderFabrikamBase_Extension.xml", CLASS_TEMPLATE.format(
            name="ContosoHeaderFabrikamBase_Extension",
            declaration="[ExtensionOf(tableStr(ContosoHeader))]\nfinal class ContosoHeaderFabrikamBase_Extension\n{\n}"
        ).replace("<Methods />", "<Methods><Method><Name>fabrikamRisk</Name><Source><![CDATA[\n"
                  "public FabrikamRisk fabrikamRisk()\n{\n}\n]]></Source></Method></Methods>"))
        write(self.src, "FabrikamBase/FabrikamBase/AxClass/FabrikamRisk.xml", CLASS_TEMPLATE.format(
            name="FabrikamRisk", declaration="public class FabrikamRisk\n{\n}").replace(
            "<Methods />", "<Methods><Method><Name>calc</Name><Source><![CDATA[\npublic ContosoTaxCalc calc()\n{\n}\n]]>"
            "</Source></Method><Method><Name>make</Name><Source><![CDATA[\npublic static ContosoBankRate make()\n{\n}\n]]>"
            "</Source></Method></Methods>"))

    def test_a_method_another_model_adds_needs_that_model(self):
        for binary in (False, True):
            with self.subTest(binary=binary):
                self.add_called_types()
                self.add_base_model(binary)
                self.code("ContosoHeader header;\n    return header.fabrikamRisk().calc() != null;")
                refs = ["ContosoSuite", "ContosoPlatform", "ContosoRetail", "ContosoBank"]
                code, out, _ = self.model(refs)
                self.assertEqual(code, 1)
                self.assertIn("FabrikamBase: ContosoLineFabrikam_Extension.fabrikamCheck calls ContosoHeader.fabrikamRisk, "
                              "which ContosoHeaderFabrikamBase_Extension adds", out)
                self.assertIn("ContosoTax: FabrikamRisk.calc uses class ContosoTaxCalc", out)
                code, out, _ = self.model(refs + ["FabrikamBase", "ContosoTax"])
                self.assertEqual(code, 0, out)

    def test_compile_log_missing_method_names_the_package_that_adds_it(self):
        self.add_called_types()
        self.add_base_model(binary=True)
        self.code("return true;")
        log = os.path.join(self.tmp.name, "xppc.log")
        Path(log).write_text("Compile Error: ClassDoesNotContainMethod: Table 'ContosoHeader' does not contain a "
                             "definition for method 'fabrikamRisk' and no extension method 'fabrikamRisk' ...\n",
                             encoding="utf-8")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"], "--compile-log", log)
        self.assertEqual(code, 1)
        self.assertIn("FabrikamBase: compiler: ContosoHeader has no method fabrikamRisk; "
                      "ContosoHeaderFabrikamBase_Extension in FabrikamBase adds it", out)

    def test_an_unreadable_file_is_a_warning_not_a_crash(self):
        write(self.src, "FabrikamExt/FabrikamExt/AxClass/Broken.xml", "<AxClass><Name>Broken")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"])
        self.assertEqual(code, 0, out)
        self.assertIn("warning: skipped 1 files that could not be read:", out)
        self.assertIn("result: OK", out)

    def test_compile_log_unknown_table_messages(self):
        log = os.path.join(self.tmp.name, "xppc.log")
        Path(log).write_text(
            "Compile Error: [(11,23),(11,49)]: The 'ContosoChannelGroup' argument of the 'tableStr' compile-time "
            "function does not specify a known table/map/view/data entity.\n"
            "Metadata Error: AxTableExtension/ContosoLine.FabrikamExt: The table 'ContosoLine' that the extension "
            "applies to does not exist.\n", encoding="utf-8")
        write(self.sdk, "ContosoRetail/ContosoRetail/AxTable/ContosoChannelGroup.xml",
              "<AxTable><Name>ContosoChannelGroup</Name></AxTable>")
        code, out, _ = self.model(["ContosoPlatform"], "--compile-log", log)
        self.assertEqual(code, 1)
        self.assertIn("ContosoRetail: compiler: ContosoChannelGroup not found; it is defined in ContosoRetail", out)
        self.assertIn("ContosoSuite: AxTableExtension/ContosoLine.FabrikamExt uses table ContosoLine", out)

    def test_compile_log_adds_only_the_package_asked_for(self):
        write(self.sdk, "ContosoSuite/Descriptor/Foundation.xml",
              descriptor("Foundation", ["ContosoPlatform", "ContosoRetail", "ContosoTax"], module="ContosoSuite"))
        log = os.path.join(self.tmp.name, "xppc.log")
        Path(log).write_text("A reference to 'Dynamics.AX.ContosoRetail, Version=0.0.0.0' is required.\n", encoding="utf-8")
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform"], "--compile-log", log)
        self.assertEqual(code, 1)
        self.assertIn("ContosoRetail: compiler: a reference to Dynamics.AX.ContosoRetail is required", out)
        self.assertIn("result: 0 errors, 1 reference to add", out)
        self.assertNotIn("ContosoTax", out)  # ContosoSuite's other references are not suggested

    def test_descriptor_problems_are_errors(self):
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "NoSuchPackage", "FabrikamExt"], publisher="Microsoft")
        self.assertEqual(code, 1)
        self.assertIn("error: reference NoSuchPackage is not a package", out)
        self.assertIn("error: the model references its own package FabrikamExt", out)
        self.assertIn("warning: Publisher is Microsoft", out)

    def test_name_already_used_by_a_standard_package(self):
        write(self.src, "ContosoRetail/Descriptor/ContosoRetail.xml", descriptor("ContosoRetail", ["ContosoSuite"]))
        code, out, _ = run("model", "ContosoRetail", "--sdk", self.sdk, "--include", self.src)
        self.assertEqual(code, 1)
        self.assertIn("error: package ContosoRetail (ContosoRetail) already exists", out)

    def test_circular_references_between_models(self):
        write(self.src, "FabrikamCore/Descriptor/FabrikamCore.xml", descriptor("FabrikamCore", ["FabrikamExt"]))
        code, out, _ = self.model(["ContosoSuite", "ContosoPlatform", "FabrikamCore"])
        self.assertEqual(code, 1)
        self.assertIn("error: circular references: FabrikamExt -> FabrikamCore -> FabrikamExt", out)

    def test_model_needs_include(self):
        code, _, err = run("model", "FabrikamExt", "--sdk", self.sdk)
        self.assertEqual(code, 2)
        self.assertIn("--include", err)


class SdkResolutionTests(unittest.TestCase):
    def test_missing_sdk_folder_is_a_usage_error(self):
        code, _, err = run("find", "table", "X", "--sdk", os.path.join(tempfile.gettempdir(), "no-such-sdk-folder"))
        self.assertEqual(code, 2)
        self.assertIn("SDK folder not found", err)

    def test_installed_sdk_is_found_and_several_need_a_version(self):
        with tempfile.TemporaryDirectory() as local:
            base = Path(local, "Microsoft", "Dynamics365")
            (base / "10.0.1.0" / "PackagesLocalDirectory").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": local}):
                roots = lookup.resolve_roots(None, None, [])
                self.assertEqual(roots, [str(base / "10.0.1.0" / "PackagesLocalDirectory")])
                (base / "10.0.2.0" / "PackagesLocalDirectory").mkdir(parents=True)
                with self.assertRaises(lookup.LookupError_) as raised:
                    lookup.resolve_roots(None, None, [])
                self.assertIn("pass --version", str(raised.exception))
                self.assertEqual(lookup.resolve_roots(None, "10.0.2.0", [])[0],
                                 str(base / "10.0.2.0" / "PackagesLocalDirectory"))

    def test_no_sdk_points_to_pac(self):
        with tempfile.TemporaryDirectory() as local:
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": local}):
                with self.assertRaises(lookup.LookupError_) as raised:
                    lookup.resolve_roots(None, None, [])
        self.assertIn("pac tool xpp install", str(raised.exception))


class HelperTests(unittest.TestCase):
    def test_split_top_level_keeps_nested_commas(self):
        self.assertEqual(lookup.split_top_level('int a = 1, str b = strFmt("%1,%2", x, y)'),
                         ["int a = 1", 'str b = strFmt("%1,%2", x, y)'])

    def test_wrapper_signature_drops_attributes_and_defaults(self):
        self.assertEqual(lookup.wrapper_signature("[SysObsolete('x', false)] public static void run(Args _args = null)"),
                         "public static void run(Args _args)")

    @unittest.skipUnless(os.name == "nt", "Windows long-path prefix")
    def test_long_path_prefix_on_windows(self):
        self.assertTrue(lookup.long_path("C:\\x\\y.xml").startswith("\\\\?\\"))


if __name__ == "__main__":
    unittest.main()
