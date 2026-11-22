# Extending standard objects

Most Finance and Operations customization changes standard behavior: a new field on `SalesLine`, a column in a grid on the `SalesTable` form, a check before a line is saved. Do this with extensions. Never edit or copy a standard object's XML (overlayering); Microsoft's models are sealed.

## Look up the target first

Every extension depends on exact names and signatures from the target: the method's parameters, the grid's control name, the data source behind it, and the extensions that already exist. Get them from `scripts/xpp_lookup.py`, not from memory.

**Do not open standard XML files under `PackagesLocalDirectory`.** They are too large to read: `SalesTable.xml` is about 1.5 MB, `SalesLine.xml` about 1.2 MB. The helper reads the SDK that `pac tool xpp install` installed and prints a few lines per question. It is read-only, uses only the Python standard library, and needs no index.

Resolve `scripts/xpp_lookup.py` relative to **this skill's directory** (not the workspace) and run it with Python:

```python
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "<resolved-erp-xpp-skill-directory>/scripts/xpp_lookup.py",
        "members", "table", "SalesLine", "--member", "validateWrite",
        "--version", "<four-part-sdk-version>",
        "--include", "<root>/src",
    ],
    check=False,
)
```

`--version` picks the SDK when several are installed (`pac tool xpp list`); with one SDK it can be omitted. `--sdk <PackagesLocalDirectory>` points at any other folder. `--include <root>/src` adds the repository's own models, so your existing extensions and names count too.

| Question | Command | Prints |
|---|---|---|
| Where does the object live? | `find <kind> <Name>` | Package/Model; the descriptor must reference that package |
| What's the exact signature? | `members <kind> <Name> --member <method>` | Signature, why it can't be wrapped (if so), and the `wrapper:` signature to use |
| What does a form data source or control override? | `members form <Form> --datasource <DS> [--field <F>]` or `--control <C>` | The overridden methods and their signatures |
| Which field, EDT, field group? | `table <Name> --field <text>` | Matching fields with type, EDT, `mandatory`, and the field groups they're in |
| Where does a control go? | `form <Form> --control <text>`, or `--parent <control>` for a grid's columns | Control type, `parent=`, data source and field, and its nearest `pattern-container=` |
| What's the form's shape? | `form <Form> [--depth N]` | Form pattern and version, data sources with joins, the control tree |
| What already extends it? | `extensions <kind> <Name> [--all]` | Extension files, and classes that wrap or handle it, with the exact target |
| Does the model reference what it needs? | `model <Model> --include <root>/src [--compile-log <log>]` | Descriptor errors, and the packages to add, with the reason for each ([Model references](#model-references)) |

Kinds: `class`, `table`, `form`, `entity`, `view`, `map`, `query`, `edt`, `enum`, `menuitem-display`, `menuitem-action`, `menuitem-output`. Lists stop at `--limit` (default 40) and say how to narrow. Exit code 0 means found, 1 means not found (with similar names), and 2 means a usage or SDK problem.

By default `extensions` reads only class files whose name contains the target name. That is fast, but it misses classes named otherwise: on a 10.0.2790 SDK it found 45 of the 48 classes that extend or handle the `SalesTable` form, in about a second. `--all` reads every class file and took about 8.5 minutes there. Use it before concluding that nothing else wraps or handles a method. The helper doesn't merge extensions into the base object; it lists them. The compiler stays the final check.

## Choose the mechanism

| Need | Use |
|---|---|
| New field, index, field group or relation on a standard table | Table extension (`AxTableExtension`) |
| Change what a public or protected method does or returns | Chain of Command (CoC) |
| React to an event (inserted, validated, form initialized, control clicked) | Event handler |
| New control, or a changed property, on a standard form | Form extension (`AxFormExtension`) |
| New values on an extensible enum, or a changed EDT property | Enum or EDT extension |
| A new object | Author it normally ([authoring.md](authoring.md)) |

Prefer CoC to pre/post handlers on methods (`PreHandlerFor`, `PostHandlerFor`): CoC can read and change the method's state and result.

## Names

- Prefix every new element with the model's prefix: fields, EDTs, labels, classes, controls.
- Extension files are named `<Target>.<Model>`, for example `SalesLine.ContosoExt`.
- Extension classes are `final`, end in `_Extension`, and include the prefix so they don't clash with the other models' extensions: `SalesLineContoso_Extension`. Check with `extensions` first.
- Model references are covered in [Model references](#model-references).

## Model references

A model compiles only when its descriptor (`src/<Model>/Descriptor/<Model>.xml`) lists in `<ModuleReferences>` every package whose elements it uses. `pac package init` adds only `ApplicationPlatform`, `ApplicationFoundation` and `ApplicationSuite`. Check the model before compiling, and again after a compile fails:

```python
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "<resolved-erp-xpp-skill-directory>/scripts/xpp_lookup.py",
        "model", "<Model>", "--include", "<root>/src",
        "--compile-log", "<compile-log-path-from-the-failed-compile>",
    ],
    check=False,
)
```

Leave out `--compile-log` before the first compile. The check takes a few seconds: it lists the SDK's type folders, then reads only the standard objects the model extends or its code calls into. It reports:

- **Descriptor errors:**
  - `Name` that doesn't match the file, or `ModelModule` that doesn't match the package folder;
  - a model or package name already used in the SDK (reusing a name such as `ApplicationSuite` is never allowed);
  - references to packages that don't exist, to the model's own package, or in a circle between models.

  It also warns when `Publisher` is still the `pac package init` default, `Microsoft`.
- **References the model's own files need:** the packages of every object it extends, wraps or handles; of each class it extends; of each EDT it extends; of each field's EDT and enum; and of every table, class, view, map or enum its X++ names (declarations, `Type::`, `new`, `tableStr()`, `fieldNum()` and the like). Each comes with the file or method that needs it.
- **References the code's calls need** (`add before compiling`). The compiler loads more than the members you call:
  - an instance method call on a standard type, as in `salesLine.salesTable()`, loads every instance method signature of that type, private ones included;
  - a static call, `Type::method()`, needs only that method's signature;
  - reading a field, `x.Field`, loads nothing;
  - code that names a form (`formStr`, `formDataSourceStr` and the like, in a CoC class or an event handler) loads the form, which resolves the fields of its view data sources. A form extension alone doesn't.

  Each package that defines a table, class, view, map or enum met this way must be referenced. EDTs and field types never count. The check follows call chains through return types, so `this.salesTable().custTable_CustAccount()` covers `SalesLine` and `SalesTable`. The compiler reports these packages one per failed compile. The check lists them all, including those already referenced, so a reference nothing needs stands out.
- **References the compiler asked for:** from `A reference to 'Dynamics.AX.<Package>' is required`, and from a type that `is not found` or `does not specify a known table`, which the check finds in its package.

**Example.** A model with `SalesLine` and `CustTable` table extensions, a `SalesTable` grid column, two CoC wrappers and an event handler (the samples below) used only `ApplicationPlatform` and `ApplicationSuite` directly. Compiled with `pac`'s three default references, it failed 7 times, each time naming one more package:
- `Retail`, for an enum behind a view data source on the `SalesTable` form, which the data source's CoC class names;
- `Directory`, `SourceDocumentationTypes`, `ContactPerson`, `Ledger`, `FiscalBooks` and `Tax`, for methods of `SalesLine` and `SalesTable`, which the code calls methods on.

Before any compile, the check listed exactly those 7, each with the member that needs it. With them the model compiled cleanly.

**Other models and ISV solutions.** Calling a method that another model's CoC class adds, such as an ISV's or another of your own models', needs that model's package. The compiler doesn't say so; it reports `Table 'X' does not contain a definition for method 'y'`. The check finds the CoC class and names its package, both before compiling and from that compile-log message. It reads every class under `--include`, and classes named after the target in the SDK.

An ISV solution shipped as binaries has no source. It has a `Descriptor`, `bin` and compiled metadata in `XppMetadata`. The check reads that compiled metadata, which holds the same signatures, so put the ISV packages under the SDK folder or pass their folder with `--include`. An enum defined only in a binary package isn't visible to the check, so the compiler's message is the guide there.

The check doesn't read menu items, security objects or reports, and it follows only typed variables, parameters, `this` and `Type::` calls. The compile log covers anything else.

So: add what the check lists, then compile. Add nothing else: each extra reference is a dependency the model doesn't need, and it slows the build. If the compiler still asks for a package, rerun the check with `--compile-log` and add the one it names.

Don't fix these errors by changing the code or by removing the extension.

## Chain of Command

```xpp
[ExtensionOf(tableStr(SalesLine))]
final class SalesLineContoso_Extension
{
    public boolean validateWrite(boolean _skipCreditLimitCheck)
    {
        boolean ret = next validateWrite(_skipCreditLimitCheck);
        // add checks here (see "Validation and required fields")
        return ret;
    }
}
```

- The target function names what is wrapped: `classStr(C)`, `tableStr(T)` (also for data entities), `formStr(F)`, `formDataSourceStr(F, DS)`, `formDataFieldStr(F, DS, Field)`, `formControlStr(F, Control)`.
- **Same signature as the base method, without default values.** `SalesLine.validateWrite` is `validateWrite(boolean _skipCreditLimitCheck = false)`, so the wrapper is `validateWrite(boolean _skipCreditLimitCheck)`. The `wrapper:` line from `members` gives it.
- Call `next` exactly once, as a first-level statement: not inside `if`, a loop or a logical expression, and not after `return`. Inside `try`/`catch`/`finally` is allowed.
- Methods that can't be wrapped: `private`, `[Hookable(false)]`, `[Wrappable(false)]`, and `final` unless marked `[Wrappable(true)]`. `members` reports these. `[Replaceable]` methods may skip `next`.
- Static methods are wrapped with `static`, except on forms.
- On form data sources, data fields and controls, wrap the kernel methods (`init`, `active`, `validateWrite`, `write`, `modified`, `validate`, `clicked`, `lookup`, ...). CoC on a plain X++ method declared inside a form data source or control compiles but isn't called at runtime.
- Check the form's override first: `SalesTable`'s `SalesLine` data source overrides `active` as `int active(boolean _mcrFormPartUpdateOnly = false)`, so a wrapper there is `int active(boolean _mcrFormPartUpdateOnly)`, not `int active()`.

The class file follows the `AxClass` layout in [authoring.md](authoring.md): the attribute and class declaration go in `<Declaration>`, and each wrapper method in `<Methods>`.

## Validation and required fields

Follow the standard user experience:

- **Always required:** set `<Mandatory>Yes</Mandatory>` on the field. Every form shows the required marker, and the platform refuses the save with its standard message. No code is needed.
- **Required only in some cases:** set the marker from the form data source, as standard `SalesTable` does (`mcrSalesTable_ds.object(fieldNum(MCRSalesTable, SourceId)).mandatory(isSourceCodeRequired)`), and check it in `validateWrite`.
- **Report with `checkFailed`, never `throw error`, in `validate*` methods.** `checkFailed` adds a warning to the Infolog and returns `false`, so the user can fix the record and save again. Put the message in a label.

```xpp
[ExtensionOf(tableStr(SalesLine))]
final class SalesLineContoso_Extension
{
    public boolean contosoLineRefRequired()
    {
        return this.salesTable().custTable_CustAccount().ContosoRequireLineRef == NoYes::Yes;
    }

    public boolean validateWrite(boolean _skipCreditLimitCheck)
    {
        boolean ret = next validateWrite(_skipCreditLimitCheck);

        if (!this.ContosoCustLineRef && this.contosoLineRefRequired())
        {
            ret = checkFailed("@ContosoExt:CustLineRefRequired");
        }

        return ret;
    }
}

[ExtensionOf(formDataSourceStr(SalesTable, SalesLine))]
final class SalesTableFormSalesLineDsContoso_Extension
{
    public int active(boolean _mcrFormPartUpdateOnly)
    {
        // SalesTable's SalesLine data source overrides active with this parameter
        int ret = next active(_mcrFormPartUpdateOnly);
        SalesLine salesLine = this.cursor();

        this.object(fieldNum(SalesLine, ContosoCustLineRef)).mandatory(salesLine.contosoLineRefRequired());
        return ret;
    }
}
```

## Table extension

Create `AxTableExtension/SalesLine.ContosoExt.xml`. Add only what's new, and keep the empty elements as the standard extensions do:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxTableExtension xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>SalesLine.ContosoExt</Name>
  <FieldGroupExtensions />
  <FieldGroups />
  <FieldModifications />
  <Fields>
    <AxTableField xmlns="" i:type="AxTableFieldString">
      <Name>ContosoCustLineRef</Name>
      <ExtendedDataType>ContosoCustLineRef</ExtendedDataType>
    </AxTableField>
  </Fields>
  <FullTextIndexes />
  <Indexes />
  <Mappings />
  <PropertyModifications />
  <RelationExtensions />
  <RelationModifications />
  <Relations />
</AxTableExtension>
```

- Base each field on an EDT (new or existing), which carries the label, help text and size. Add `<Mandatory>Yes</Mandatory>` when the field is always required.
- A new field needs a DB sync after deployment: `--db-sync Module --modules <Model>` (see `SKILL.md`).
- A `display` method for a form goes on the table extension class (`public display <EDT> contosoName()`), and the form control binds it with `DataMethod`.

## Form extension

Find the parent first: `form SalesTable --control Grid` lists the grids, for example `SalesLineGrid [Grid DataSource=SalesLine] parent=LineViewLines`, and `form SalesTable --parent SalesLineGrid` lists the grid's columns for `PreviousSibling`. Then create `AxFormExtension/SalesTable.ContosoExt.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxFormExtension xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns="Microsoft.Dynamics.AX.Metadata.V6">
  <Name>SalesTable.ContosoExt</Name>
  <ControlModifications />
  <Controls>
    <AxFormExtensionControl xmlns="">
      <Name>ContosoCustLineRefControl</Name>
      <FormControl xmlns="" i:type="AxFormStringControl">
        <Name>SalesLine_ContosoCustLineRef</Name>
        <Type>String</Type>
        <FormControlExtension i:nil="true" />
        <DataField>ContosoCustLineRef</DataField>
        <DataSource>SalesLine</DataSource>
      </FormControl>
      <Parent>SalesLineGrid</Parent>
      <PositionType>AfterItem</PositionType>
      <PreviousSibling>EXISTING_GRID_CONTROL_NAME</PreviousSibling>
    </AxFormExtensionControl>
  </Controls>
  <DataSourceModifications />
  <DataSourceReferences />
  <DataSources />
  <Parts />
  <PropertyModifications />
</AxFormExtension>
```

- `<Parent>` is the exact control name from `form --control`; `DataSource` is the grid's data source. Take `PreviousSibling` from the same lookup, or omit the two position elements.
- Respect the form pattern. `form` prints the form's pattern and each control's nearest `pattern-container=`; add controls only where that pattern allows them, for example a field group inside a `FieldsFieldGroups` tab page.
- `ControlModifications` and `PropertyModifications` change existing controls and the form; `DataSources` adds a data source and `DataSourceModifications` changes one.

## Event handlers

Use a handler to react to an event without changing the method's result. Handlers are `public static` methods on a class; copy the signature the event requires:

```xpp
class SalesLineContosoEventHandler
{
    [DataEventHandler(tableStr(SalesLine), DataEventType::ValidatedWrite)]
    public static void SalesLine_onValidatedWrite(Common _sender, DataEventArgs _e)
    {
        SalesLine salesLine = _sender;
        ValidateEventArgs validateEventArgs = _e as ValidateEventArgs;

        if (!salesLine.ContosoCustLineRef && salesLine.contosoLineRefRequired())
        {
            validateEventArgs.parmValidateResult(checkFailed("@ContosoExt:CustLineRefRequired"));
        }
    }

    [FormControlEventHandler(formControlStr(SalesTable, CONTROL_NAME), FormControlEventType::Clicked)]
    public static void CONTROL_NAME_OnClicked(FormControl _sender, FormControlEventArgs _e)
    {
    }
}
```

Form handlers use `[FormEventHandler(formStr(F), FormEventType::...)]`, `[FormDataSourceEventHandler(formDataSourceStr(F, DS), FormDataSourceEventType::...)]` and `[FormControlEventHandler(...)]`. Delegates are subscribed with `[SubscribesTo(classStr(C), delegateStr(C, delegateName))]`.

## Common mistakes

| Wrong | Correct |
|---|---|
| Editing or copying the standard object's XML | An extension in your own model |
| Reading `SalesTable.xml` into context to find a control | `xpp_lookup.py form SalesTable --control <text>` |
| `validateWrite()` from memory | The `wrapper:` signature from `members`: `validateWrite(boolean _skipCreditLimitCheck)` |
| Repeating the default value in the wrapper (`= false`) | Same parameters, no default values |
| `next` inside `if`, or skipped | One unconditional first-level `next` call |
| Wrapping a `private`, `final` or `[Wrappable(false)]` method | A wrappable method, an event or a delegate the lookup shows |
| `throw error("...")` in `validateWrite` | `ret = checkFailed("@Label:Id");` |
| A required field with no marker | `Mandatory = Yes`, or `mandatory()` on the form data source field |
| A guessed grid name or parent | The exact `parent=` from `form --control` |
| A second `SalesLine_Extension` class | A unique, prefixed name, checked with `extensions` |
| A new table field deployed without DB sync | Module DB sync for the model |
| Changing code to get past `A reference to 'Dynamics.AX.<Package>' is required` | Add the package to `<ModuleReferences>` (`xpp_lookup.py model --compile-log`) |
| Adding packages "just in case", or copying another model's reference list | Only the packages `xpp_lookup.py model` or the compiler names |
| A model named like a standard package, or `Publisher` left as `Microsoft` | A unique, prefixed model name and your own publisher |
