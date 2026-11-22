"""Answer small questions about X++ metadata without reading whole AOT files.

The SDK that `pac tool xpp install` places under
%LOCALAPPDATA%\\Microsoft\\Dynamics365\\<version>\\PackagesLocalDirectory holds every
standard object as XML (<Package>\\<Model>\\AxForm\\SalesTable.xml). Those files are too
large to read into an agent's context, so each command here prints a few lines:

  find        which package and model hold an object
  members     method signatures, with wrapping notes and the wrapper signature
  table       fields (type, EDT, mandatory) and the field groups they are in
  form        the form pattern, data sources and controls
  extensions  extension files and classes that extend or handle an object
  model       a model's descriptor: name, publisher, references that are missing or wrong

Read-only. Standard library only. Exit codes: 0 found, 1 not found, 2 usage or SDK problem.
"""

import argparse
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
DEFAULT_LIMIT = 40

KINDS = {
    "class": "AxClass",
    "table": "AxTable",
    "form": "AxForm",
    "entity": "AxDataEntityView",
    "view": "AxView",
    "map": "AxMap",
    "query": "AxQuery",
    "edt": "AxEdt",
    "enum": "AxEnum",
    "menuitem-display": "AxMenuItemDisplay",
    "menuitem-action": "AxMenuItemAction",
    "menuitem-output": "AxMenuItemOutput",
}

EXTENSION_FOLDERS = {
    "table": "AxTableExtension",
    "form": "AxFormExtension",
    "entity": "AxDataEntityViewExtension",
    "view": "AxViewExtension",
    "map": "AxMapExtension",
    "query": "AxQuerySimpleExtension",
    "edt": "AxEdtExtension",
    "enum": "AxEnumExtension",
    "menuitem-display": "AxMenuItemDisplayExtension",
    "menuitem-action": "AxMenuItemActionExtension",
    "menuitem-output": "AxMenuItemOutputExtension",
}

# Attributes that tie a class to another object: Chain of Command and event handlers.
LINK_ATTRIBUTES = (
    "ExtensionOf|DataEventHandler|PreHandlerFor|PostHandlerFor|SubscribesTo|FormEventHandler"
    "|FormDataSourceEventHandler|FormDataFieldEventHandler|FormControlEventHandler"
)
# The intrinsic functions that name each kind of target in those attributes.
LINK_TARGETS = {
    "class": "classStr",
    "table": "tableStr",
    "entity": "tableStr|dataEntityDataSourceStr",
    "view": "tableStr|viewStr",
    "map": "mapStr",
    "form": "formStr|formDataSourceStr|formDataFieldStr|formControlStr",
}


class LookupError_(Exception):
    """A problem the caller can fix: bad SDK path, ambiguous version, unknown kind."""


# ---------------------------------------------------------------- files and XML

def long_path(path):
    """SDK paths can exceed MAX_PATH on Windows; the \\\\?\\ prefix lifts the limit."""
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def load(path):
    """Parse an AOT file and drop namespaces (forms set a default one and reset it inside)."""
    with open(long_path(path), "rb") as handle:
        root = ET.parse(handle).getroot()
    for element in root.iter():
        element.tag = element.tag.split("}", 1)[-1]
    return root


UNREADABLE = []


def safe_load(path):
    """load(), but a file that can't be read or parsed becomes an empty element and is reported,
    so one bad file in a model never stops the model check."""
    try:
        return load(path)
    except (ET.ParseError, OSError, UnicodeDecodeError) as error:
        UNREADABLE.append(f"{path} ({error})")
        return ET.Element("Unreadable")


def resolve_roots(sdk, version, include):
    """The metadata roots to search: the SDK's PackagesLocalDirectory plus --include folders."""
    roots = []
    if sdk:
        if not os.path.isdir(sdk):
            raise LookupError_(f"SDK folder not found: {sdk}")
        roots.append(sdk)
    else:
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Dynamics365")
        found = sorted(
            name for name in (os.listdir(base) if os.path.isdir(base) else [])
            if os.path.isdir(os.path.join(base, name, "PackagesLocalDirectory"))
        )
        if version:
            if version not in found:
                raise LookupError_(
                    f"No SDK {version} under {base}. Installed: {', '.join(found) or 'none'}. "
                    "Install it with `pac tool xpp install`."
                )
            chosen = version
        elif len(found) == 1:
            chosen = found[0]
        elif not found:
            raise LookupError_(f"No SDK under {base}. Install one with `pac tool xpp install`, or pass --sdk.")
        else:
            raise LookupError_(f"Several SDKs installed ({', '.join(found)}); pass --version.")
        roots.append(os.path.join(base, chosen, "PackagesLocalDirectory"))
    for folder in include or []:
        if not os.path.isdir(folder):
            raise LookupError_(f"--include folder not found: {folder}")
        roots.append(folder)
    return roots


def object_files(roots, folder, pattern):
    """<root>/<Package>/<Model>/<folder>/<pattern>.xml in every root."""
    hits = []
    for root in roots:
        hits.extend(glob.glob(os.path.join(root, "*", "*", folder, pattern + ".xml")))
    return sorted(hits)


def location(path):
    """Package/Model of an AOT file path."""
    parts = os.path.normpath(path).split(os.sep)
    return f"{parts[-4]}/{parts[-3]}"


def require_one(roots, kind, name):
    if kind not in KINDS:
        raise LookupError_(f"Unknown kind {kind!r}. Kinds: {', '.join(KINDS)}.")
    files = object_files(roots, KINDS[kind], name)
    if not files:
        return None, not_found(roots, kind, name)
    return files[0], None


def not_found(roots, kind, name):
    near = [os.path.basename(p)[:-4] for p in object_files(roots, KINDS[kind], f"*{name}*")]
    lines = [f"No {kind} named {name}."]
    if near:
        lines.append("Similar names: " + ", ".join(sorted(set(near))[:15]))
    return lines


def capped(rows, limit, hint):
    if len(rows) <= limit:
        return rows
    return rows[:limit] + [f"... {len(rows) - limit} more; {hint}"]


# ---------------------------------------------------------------- signatures

def signature(source):
    """Attribute lines plus the declaration up to the opening brace, comments dropped."""
    parts = []
    for raw in (source or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or (line.startswith("using ") and line.endswith(";")):
            continue
        if line.startswith("{"):
            break
        parts.append(line.split("{", 1)[0])
        if "{" in line:
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def split_top_level(text):
    """Split a parameter list on commas that are not inside brackets or quotes."""
    items, depth, quote, current = [], 0, "", []
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        items.append("".join(current).strip())
    return items


def wrapper_signature(sig):
    """The CoC wrapper's declaration: same parameters, default values removed, no attributes."""
    declaration = re.sub(r"^(\[[^\]]*\]\s*)+", "", sig)
    match = re.search(r"\((.*)\)\s*$", declaration)
    if not match:
        return None
    params = [p.split("=", 1)[0].strip() for p in split_top_level(match.group(1))]
    return declaration[: match.start()] + "(" + ", ".join(params) + ")"


def wrap_notes(sig):
    low = sig.lower()
    notes = []
    if re.search(r"\bprivate\b", low):
        notes.append("private: cannot be wrapped")
    if "hookable(false)" in low:
        notes.append("Hookable(false): no CoC and no event handlers")
    if "wrappable(false)" in low:
        notes.append("Wrappable(false): cannot be wrapped")
    elif re.search(r"\bfinal\b", re.sub(r"^(\[[^\]]*\]\s*)+", "", low)) and "wrappable(true)" not in low:
        notes.append("final: cannot be wrapped unless marked [Wrappable(true)]")
    if "replaceable" in low:
        notes.append("Replaceable: a wrapper may skip next")
    return notes


def describe_method(method):
    sig = signature(method.findtext("Source"))
    rows = [sig]
    notes = wrap_notes(sig)
    if notes:
        rows.append("  note: " + "; ".join(notes))
    elif "=" in sig.split("(", 1)[-1]:
        wrapper = wrapper_signature(sig)
        if wrapper:
            rows.append("  wrapper: " + wrapper)
    return rows


def method_elements(container):
    return container.findall("Methods/Method") if container is not None else []


# ---------------------------------------------------------------- commands

def cmd_find(roots, args):
    if args.kind not in KINDS:
        raise LookupError_(f"Unknown kind {args.kind!r}. Kinds: {', '.join(KINDS)}.")
    files = object_files(roots, KINDS[args.kind], args.name)
    if not files:
        return 1, not_found(roots, args.kind, args.name)
    return 0, [f"{args.kind} {args.name}: {location(p)} ({os.path.getsize(long_path(p)):,} bytes)" for p in files]


def form_member_container(root, args):
    """The element whose Methods hold what was asked: form, data source, data field or control."""
    source = root.find("SourceCode")
    if source is None:
        return None, "form (no source code)"
    if args.control:
        for control in source.findall("DataControls/Control"):
            if (control.findtext("Name") or "").lower() == args.control.lower():
                return control, f"control {args.control}"
        return None, f"control {args.control} (no overridden methods)"
    if args.datasource:
        for ds in source.findall("DataSources/DataSource"):
            if (ds.findtext("Name") or "").lower() != args.datasource.lower():
                continue
            if args.field:
                for field in ds.findall("Fields/Field"):
                    if (field.findtext("DataField") or "").lower() == args.field.lower():
                        return field, f"data source {args.datasource} field {args.field}"
                return None, f"data source {args.datasource} field {args.field} (no overridden methods)"
            return ds, f"data source {args.datasource}"
        return None, f"data source {args.datasource} (no overridden methods)"
    return source, "form"


def cmd_members(roots, args):
    path, missing = require_one(roots, args.kind, args.name)
    if missing:
        return 1, missing
    root = load(path)
    rows = [f"{args.kind} {args.name} ({location(path)})"]
    if args.kind == "form":
        container, label = form_member_container(root, args)
        rows[0] += f", {label}"
        if args.datasource or args.control:
            rows.append("  Kernel methods (init, active, validateWrite, write, modified, clicked, ...) can be "
                        "wrapped even when not listed here.")
    else:
        container = root.find("SourceCode")
        declaration = signature(root.findtext("SourceCode/Declaration"))
        if declaration:
            rows.append(declaration)
    methods = method_elements(container)
    if args.member:
        chosen = [m for m in methods if (m.findtext("Name") or "").lower() == args.member.lower()]
        if not chosen:
            names = sorted(m.findtext("Name") for m in methods)
            rows.append(f"No method {args.member} here. Methods: " + (", ".join(names[:60]) or "none"))
            return 1, rows
        for method in chosen:
            rows.extend(describe_method(method))
        return 0, rows
    sigs = [signature(m.findtext("Source")) for m in methods]
    rows.append(f"methods ({len(sigs)}):")
    rows.extend(capped(sorted(sigs, key=str.lower), args.limit, "pass --member <name>"))
    return 0, rows


def field_row(field):
    kind = (field.get(XSI_TYPE) or "").replace("AxTableField", "") or "?"
    bits = [kind]
    for tag in ("ExtendedDataType", "EnumType"):
        value = field.findtext(tag)
        if value:
            bits.append(value)
    if field.findtext("Mandatory") == "Yes":
        bits.append("mandatory")
    return f"{field.findtext('Name')} [{' '.join(bits)}]"


def cmd_table(roots, args):
    path, missing = require_one(roots, "table", args.name)
    if missing:
        return 1, missing
    root = load(path)
    fields = root.findall("Fields/AxTableField")
    groups = root.findall("FieldGroups/AxTableFieldGroup")
    rows = [f"table {args.name} ({location(path)}): {len(fields)} fields, {len(groups)} field groups"]
    if args.field:
        wanted = args.field.lower()
        matched = [f for f in fields if wanted in (f.findtext("Name") or "").lower()]
        rows.append(f"fields matching {args.field!r} ({len(matched)}):")
        shown = []
        for field in matched:
            name = field.findtext("Name")
            in_groups = [g.findtext("Name") for g in groups
                         if any(x.findtext("DataField") == name for x in g.findall("Fields/AxTableFieldGroupField"))]
            shown.append("  " + field_row(field) + (f" groups: {', '.join(in_groups)}" if in_groups else ""))
        rows.extend(capped(shown, args.limit, "narrow --field"))
    else:
        rows.append("fields: " + ", ".join(capped([field_row(f) for f in fields], args.limit, "pass --field <text>")))
        rows.append("field groups: " + ", ".join(g.findtext("Name") for g in groups[: args.limit]))
        rows.append("indexes: " + ", ".join(i.findtext("Name") for i in root.findall("Indexes/AxTableIndex")))
    extensions = object_files(roots, EXTENSION_FOLDERS["table"], args.name + ".*")
    if extensions:
        rows.append(f"{len(extensions)} table extensions add to this table: run `extensions table {args.name}`")
    return 0, rows


def control_row(control, depth, parent, container):
    kind = (control.get(XSI_TYPE) or "").replace("AxForm", "").replace("Control", "") or "Custom"
    bits = [kind]
    for tag in ("Pattern", "PatternVersion", "DataSource", "DataField", "DataMethod", "DataGroup"):
        value = control.findtext(tag)
        if value:
            bits.append(f"{tag}={value}")
    where = f"parent={parent}"
    if container:
        where += f" pattern-container={container}"
    return "  " * depth + f"{control.findtext('Name')} [{' '.join(bits)}] {where}"


def walk(control, depth, parent, container, wanted, max_depth, out):
    """Depth-first over the design; `container` is the nearest ancestor that sets a pattern.

    `wanted(name, parent)` selects controls; without it the tree is listed to `max_depth`.
    """
    name = control.findtext("Name")
    if wanted is None:
        if depth <= max_depth:
            out.append(control_row(control, depth, parent, container))
    elif wanted(name or "", parent or ""):
        out.append(control_row(control, 0, parent, container))
    pattern = control.findtext("Pattern")
    child_container = f"{name}({pattern})" if pattern else container
    for child in control.findall("Controls/AxFormControl"):
        walk(child, depth + 1, name, child_container, wanted, max_depth, out)


def data_source_label(ds):
    name, table, join = ds.findtext("Name"), ds.findtext("Table"), ds.findtext("JoinSource")
    text = name if table in (None, name) else f"{name}={table}"
    return f"{text}<{join}" if join else text


def cmd_form(roots, args):
    path, missing = require_one(roots, "form", args.name)
    if missing:
        return 1, missing
    root = load(path)
    design = root.find("Design")
    pattern = " ".join(x for x in (design.findtext("Pattern"), design.findtext("PatternVersion")) if x)
    rows = [f"form {args.name} ({location(path)}), pattern: {pattern or 'none'}"]
    wanted, label = None, f"to depth {args.depth}"
    if args.control:
        text = args.control.lower()
        wanted, label = (lambda name, parent: text in name.lower()), f"matching {args.control!r}"
    elif args.parent:
        exact = args.parent.lower()
        wanted, label = (lambda name, parent: parent.lower() == exact), f"directly under {args.parent}"
    else:
        sources = [data_source_label(ds) for ds in root.findall("DataSources/AxFormDataSource")]
        rows.append(f"data sources ({len(sources)}; Name=Table<JoinSource): "
                    + ", ".join(capped(sources, args.limit, "use --limit")))
    out = []
    for control in design.findall("Controls/AxFormControl"):
        walk(control, 0, "Design", None, wanted, args.depth, out)
    rows.append(f"controls {label} ({len(out)}):")
    rows.extend(capped(out, args.limit, "pass --control <text>, --parent <control> or a smaller --depth"))
    extensions = object_files(roots, EXTENSION_FOLDERS["form"], args.name + ".*")
    if extensions:
        rows.append(f"{len(extensions)} form extensions add to this form: run `extensions form {args.name}`")
    return 0, rows


def linked_classes(roots, kind, name, scan_all):
    """Classes whose source ties them to `name` through CoC or an event handler attribute."""
    needle = re.compile(
        r"\[\s*(" + LINK_ATTRIBUTES + r")\s*\(\s*(" + LINK_TARGETS[kind] + r")\s*\(\s*("
        + re.escape(name) + r"\b[^)]*)\)",
        re.IGNORECASE,
    )
    raw_name = name.lower().encode("ascii", "ignore")
    pattern = "*" if scan_all else f"*{name}*"
    files = object_files(roots, "AxClass", pattern)
    hits = []
    for path in files:
        with open(long_path(path), "rb") as handle:
            data = handle.read()
        if raw_name not in data.lower():
            continue
        links = sorted({f"{m.group(1)} {m.group(2)}({m.group(3).strip()})"
                        for m in needle.finditer(data.decode("utf-8", "ignore"))})
        if links:
            hits.append(f"  {os.path.basename(path)[:-4]} ({location(path)}): {'; '.join(links)}")
    return len(files), hits


def cmd_extensions(roots, args):
    if args.kind not in KINDS:
        raise LookupError_(f"Unknown kind {args.kind!r}. Kinds: {', '.join(KINDS)}.")
    rows = []
    folder = EXTENSION_FOLDERS.get(args.kind)
    if folder:
        files = object_files(roots, folder, args.name + ".*")
        rows.append(f"{folder} for {args.name} ({len(files)}):")
        rows.extend(capped([f"  {os.path.basename(p)[:-4]} ({location(p)})" for p in files], args.limit, "use --limit"))
    if args.kind not in LINK_TARGETS:
        return 0, rows
    scanned, hits = linked_classes(roots, args.kind, args.name, args.all)
    scope = "every class file" if args.all else f"class files named *{args.name}*; --all scans every class"
    rows.append(f"classes that extend or handle {args.kind} {args.name} ({len(hits)}; scanned {scanned} {scope}):")
    rows.extend(capped(sorted(hits, key=str.lower), args.limit, "use --limit"))
    return 0, rows


# ---------------------------------------------------------------- model references

EXTENSION_TARGET_KIND = {folder.lower(): kind for kind, folder in EXTENSION_FOLDERS.items()}
LINK_FUNCTION_KINDS = {
    "classstr": ("class",), "tablestr": ("table", "entity", "view"), "viewstr": ("view",), "mapstr": ("map",),
    "formstr": ("form",), "formdatasourcestr": ("form",), "formdatafieldstr": ("form",), "formcontrolstr": ("form",),
    "dataentitydatasourcestr": ("entity",),
}
TYPE_KINDS = ("enum", "edt", "table", "class", "view", "map", "entity", "form", "query")
LINK_IN_SOURCE = re.compile(
    r"\[\s*(?:" + LINK_ATTRIBUTES + r")\s*\(\s*(\w+)\s*\(\s*(\w+)", re.IGNORECASE)
CLASS_EXTENDS = re.compile(r"\bclass\s+\w+\s+extends\s+(\w+)", re.IGNORECASE)
COMPILER_REFERENCE = re.compile(r"A reference to '(?:Dynamics\.AX\.)?([A-Za-z0-9_]+)[,']", re.IGNORECASE)
COMPILER_MISSING_METHOD = re.compile(
    r"(?:Table|Class|View|Map) '(\w+)' does not contain a definition for method '(\w+)'", re.IGNORECASE)
COMPILER_MISSING_TYPE = re.compile(
    r"(?:Enum type|Extended data type|Table|Class|View|Map|Type)\s+'(\w+)'[^\n]*?\bnot found"
    r"|The name '(\w+)' does not denote"
    r"|The '(\w+)' argument of the '\w+' compile-time function does not specify a known"
    r"|The \w+ '(\w+)' that the extension applies to does not exist", re.IGNORECASE)
# Types the kernel defines, so no package holds them.
KERNEL_TYPES = {"noyes", "common", "object", "args", "anytype"}


def compiled_files(roots, folder, pattern):
    """<root>/<Package>/XppMetadata/<Model>/<folder>/<pattern>.xml: the compiled metadata a binary package
    (an ISV solution shipped without source, for example) has instead of source files."""
    hits = []
    for root in roots:
        hits.extend(glob.glob(os.path.join(root, "*", "XppMetadata", "*", folder, pattern + ".xml")))
    return sorted(hits)


def package_from_path(path):
    parts = os.path.normpath(path).split(os.sep)
    return parts[-5] if len(parts) >= 5 and parts[-4].lower() == "xppmetadata" else parts[-4]


def package_of(roots, kinds, name, cache):
    """Package that defines `name` as the first matching kind, or None (kernel type or misspelling)."""
    for kind in kinds:
        key = (kind, name.lower())
        if key not in cache:
            files = object_files(roots, KINDS[kind], name) or compiled_files(roots, KINDS[kind], name)
            cache[key] = package_from_path(files[0]) if files else None
        if cache[key]:
            return cache[key]
    return None


def read_descriptor(path):
    root = load(path)
    refs = [(s.text or "").strip() for s in root.findall("ModuleReferences/string")]
    return {
        "name": root.findtext("Name") or "", "module": root.findtext("ModelModule") or "",
        "publisher": root.findtext("Publisher") or "", "layer": root.findtext("Layer") or "",
        "refs": [r for r in refs if r],
    }


def model_needs(roots, package_dir, model, cache):
    """Packages the model's own metadata uses directly, each with the first file that needs it, and the
    names no package defines."""
    needs, unresolved = {}, set()

    def need(kinds, name, where):
        if name.lower() in KERNEL_TYPES:
            return
        package = package_of(roots, kinds, name, cache)
        if package:
            needs.setdefault(package, f"{where} uses {kinds[0]} {name}")
        else:
            unresolved.add(name)

    for path in sorted(glob.glob(os.path.join(package_dir, model, "Ax*", "*.xml"))):
        folder = os.path.basename(os.path.dirname(path))
        where = f"{folder}/{os.path.basename(path)[:-4]}"
        if folder.lower() in EXTENSION_TARGET_KIND:
            need((EXTENSION_TARGET_KIND[folder.lower()],), os.path.basename(path).split(".")[0], where)
        if folder.lower() == "axclass":
            with open(long_path(path), "rb") as handle:
                text = handle.read().decode("utf-8", "ignore")
            for function, target in LINK_IN_SOURCE.findall(text):
                need(LINK_FUNCTION_KINDS.get(function.lower(), TYPE_KINDS), target, where)
            for base in CLASS_EXTENDS.findall(text):
                need(("class",), base, where)
            continue
        root = safe_load(path)
        if folder.lower() == "axedt" and root.findtext("Extends"):
            need(("edt",), root.findtext("Extends"), where)
        for field in root.findall("Fields/AxTableField"):
            if field.findtext("ExtendedDataType"):
                need(("edt",), field.findtext("ExtendedDataType"), where)
            if field.findtext("EnumType"):
                need(("enum",), field.findtext("EnumType"), where)
        for ds in root.findall("DataSources/AxFormDataSource"):
            if ds.findtext("Table"):
                need(("table", "view", "entity"), ds.findtext("Table"), where)
    return needs, unresolved


# What the compiler loads for the model's X++ code, as measured with xppc:
# - an instance method call on a standard type (x.m()) loads every instance method signature of that
#   type, private ones included;
# - a static call (T::m()) needs only m's own signature; reading a field (x.f) loads nothing;
# - code that names a form (formStr, formDataSourceStr, ...) loads the form, which resolves the fields
#   of its view data sources.
# A package that defines a table, view, map, entity, class or enum met this way must be referenced.
# EDTs and field types never count.
MEMBER_TYPE_KINDS = ("table", "view", "map", "entity", "class")
SIGNATURE_TYPE_KINDS = MEMBER_TYPE_KINDS + ("enum",)
HANDLER_ATTRIBUTE = re.compile(
    r"\[\s*(?:SubscribesTo|DataEventHandler|PreHandlerFor|PostHandlerFor|FormEventHandler|FormDataSourceEventHandler"
    r"|FormDataFieldEventHandler|FormControlEventHandler)\b", re.IGNORECASE)
HANDLER_NAMES = {"SubscribesTo", "DataEventHandler", "PreHandlerFor", "PostHandlerFor", "FormEventHandler",
                 "FormDataSourceEventHandler", "FormDataFieldEventHandler", "FormControlEventHandler"}
CODE_TARGETS = ("tablestr", "classstr", "viewstr", "mapstr")
CODE_TOKEN = re.compile(r"[A-Za-z_]\w*|::|\S")
WORD = re.compile(r"[A-Za-z_]\w*$")
NAMING_FUNCTIONS = re.compile(
    r"\b(?:tableStr|tableNum|fieldNum|fieldStr|classStr|classNum|enumStr|enumNum|viewStr|mapStr|tableMethodStr"
    r"|tableStaticMethodStr|staticMethodStr|methodStr)\s*\(\s*(\w+)", re.IGNORECASE)
FORM_FUNCTIONS = re.compile(
    r"\b(?:formStr|formDataSourceStr|formDataFieldStr|formControlStr|formMethodStr)\s*\(\s*(\w+)", re.IGNORECASE)
NOT_TYPES = set(
    "return new select while if else for do next this super element public private protected internal static final"
    " abstract virtual void int int64 real str boolean date utcdatetime container var const readonly display edit"
    " server client extends implements class interface throw try catch finally retry ttsbegin ttscommit ttsabort"
    " firstonly forupdate where join exists notexists outer case switch default break continue using as is in like"
    " true false null guid anytype delegate event changecompany".split())


def strip_code(source):
    """X++ source without comments and string literals, which would otherwise look like code."""
    source = re.sub(r"/\*.*?\*/", " ", source or "", flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", " ", source)
    return re.sub(r"@?\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", " 0 ", source)


def declaration_parts(sig):
    """(name, return type, [(parameter type, parameter name)], is static) of a method declaration, or None."""
    declaration = re.sub(r"^(\[[^\]]*\]\s*)+", "", sig or "")
    match = re.search(r"(\w+)\s*\((.*)\)\s*$", declaration)
    if not match:
        return None
    head = declaration[: match.start()].split()
    params = [p.split("=", 1)[0].split() for p in split_top_level(match.group(2))]
    return (match.group(1), head[-1] if head else None, [(p[-2], p[-1]) for p in params if len(p) >= 2],
            "static" in (word.lower() for word in head))


def closing_paren(tokens, start):
    """Index just after the ')' that matches tokens[start] == '('."""
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i] == "(":
            depth += 1
        elif tokens[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(tokens)


def is_compiled(path):
    return "xppmetadata" in (part.lower() for part in os.path.normpath(path).split(os.sep))


def read_methods(root, compiled):
    """(name, return type, parameter types, is static, is event handler) for each method of an object."""
    rows = []
    if compiled:
        for method in root.findall("Methods/Method"):
            attributes = {a.findtext("Name") or "" for a in method.findall("Attributes/AxAttribute")}
            rows.append((method.findtext("Name") or "", method.findtext("ReturnType/TypeName"),
                         [p.findtext("TypeName") for p in method.findall("Parameters/AxMethodParameter")],
                         (method.findtext("IsStatic") or "").lower() == "true",
                         bool(attributes & HANDLER_NAMES)))
        return rows
    for method in root.findall("SourceCode/Methods/Method"):
        sig = signature(method.findtext("Source"))
        parts = declaration_parts(sig)
        if parts:
            rows.append((parts[0], parts[1], [t for t, _ in parts[2]], parts[3], bool(HANDLER_ATTRIBUTE.search(sig))))
    return rows


def coc_target(root, compiled):
    """The table, class, view or map a CoC class extends, or None."""
    if compiled:
        for attribute in root.findall("Attributes/AxAttribute"):
            if (attribute.findtext("Name") or "").lower() == "extensionof":
                parameter = attribute.find("Parameters/AxAttributeParameter")
                if parameter is not None and (parameter.findtext("TypeValue") or "").lower() in CODE_TARGETS:
                    return parameter.findtext("AdditionalData/AxAttributeParameter/TypeValue")
        return None
    target = re.search(r"ExtensionOf\s*\(\s*(\w+)\s*\(\s*(\w+)", strip_code(root.findtext("SourceCode/Declaration")),
                       re.IGNORECASE)
    return target.group(2) if target and target.group(1).lower() in CODE_TARGETS else None


class TypeIndex:
    """Type name -> (kind, package, file) from folder listings; member signatures are read on demand."""

    FOLDERS = {"table": "AxTable", "view": "AxView", "map": "AxMap", "entity": "AxDataEntityView",
               "class": "AxClass", "enum": "AxEnum"}

    def __init__(self, roots):
        self.names = {kind: {} for kind in self.FOLDERS}
        for root in roots:
            for package in sorted(os.listdir(root)):
                package_dir = os.path.join(root, package)
                if not os.path.isdir(os.path.join(package_dir, "Descriptor")):
                    continue
                has_source = False
                for model in sorted(os.listdir(package_dir)):
                    for kind, folder in self.FOLDERS.items():
                        folder_dir = os.path.join(package_dir, model, folder)
                        if os.path.isdir(folder_dir):
                            for name in os.listdir(folder_dir):
                                if name.lower().endswith(".xml"):
                                    has_source = True  # empty Ax* folders, which builds leave behind, don't count
                                    self.names[kind].setdefault(
                                        name[:-4].lower(), (kind, package, os.path.join(folder_dir, name)))
                compiled = os.path.join(package_dir, "XppMetadata")
                if not has_source and os.path.isdir(compiled):  # a binary package: read its compiled metadata
                    for model in sorted(os.listdir(compiled)):
                        for kind, folder in self.FOLDERS.items():
                            folder_dir = os.path.join(compiled, model, folder)
                            if os.path.isdir(folder_dir):
                                for name in os.listdir(folder_dir):
                                    if name.lower().endswith(".xml"):
                                        self.names[kind].setdefault(
                                            name[:-4].lower(), (kind, package, os.path.join(folder_dir, name)))
        self.types = {}
        self.extension_methods = {}  # target type -> {method: return type}, from the model's own CoC classes
        self.include = [os.path.normcase(os.path.abspath(r)) for r in roots[1:]]  # the repo's own models
        self.added = {}  # target type -> {method: (package, class, return type)} from other CoC classes
        self.added_needs = {}  # package -> why: methods the code calls that another package's CoC class adds

    def find(self, name, kinds=None):
        for kind in kinds or self.FOLDERS:
            hit = self.names[kind].get((name or "").lower())
            if hit:
                return hit
        return None

    def type_info(self, name):
        """Package, base, methods (name -> return type), the packages all its instance method signatures
        use, and the packages each method's own signature uses."""
        key = (name or "").lower()
        if key in self.types:
            return self.types[key]
        info = self.types[key] = {"package": None, "base": None, "methods": {}, "instance": {}, "method": {}}
        hit = self.find(name, MEMBER_TYPE_KINDS)
        if not hit:
            return info
        kind, info["package"], path = hit
        compiled = is_compiled(path)
        root = safe_load(path)
        base = root.findtext("Extends")
        if not base and kind == "class" and not compiled:
            match = CLASS_EXTENDS.search(strip_code(root.findtext("SourceCode/Declaration")))
            base = match.group(1) if match else None
        info["base"] = base
        for method_name, returns, params, static, handler in read_methods(root, compiled):
            info["methods"].setdefault(method_name.lower(), returns)
            own = info["method"].setdefault(method_name.lower(), {})
            for type_name in [returns] + params:
                found = self.find(type_name, SIGNATURE_TYPE_KINDS)
                if found:
                    why = f"{name}.{method_name} uses {found[0]} {type_name}"
                    own.setdefault(found[1], why)
                    if not static and not handler:
                        info["instance"].setdefault(found[1], why)
        if base and base.lower() != key:
            parent = self.type_info(base)
            if parent["package"]:
                info["instance"].setdefault(parent["package"], f"{name} extends {base}")
            for package, why in parent["instance"].items():
                info["instance"].setdefault(package, why)
            for method_name, returns in parent["methods"].items():
                info["methods"].setdefault(method_name, returns)
                info["method"].setdefault(method_name, parent["method"].get(method_name, {}))
        return info

    def added_methods(self, type_name):
        """Methods other models' CoC classes add to a type. In the SDK only classes whose name contains the
        type's name are read (the naming convention); in --include folders every class is."""
        key = type_name.lower()
        if key not in self.added:
            self.added[key] = {}
            for name, (_, package, path) in self.names["class"].items():
                local = any(os.path.normcase(os.path.abspath(path)).startswith(r + os.sep) for r in self.include)
                if key not in name and not local:
                    continue
                compiled = is_compiled(path)
                root = safe_load(path)
                if (coc_target(root, compiled) or "").lower() != key:
                    continue
                for method_name, returns, _, _, _ in read_methods(root, compiled):
                    self.added[key].setdefault(method_name.lower(), (package, os.path.basename(path)[:-4], returns))
        return self.added[key]

    def return_type(self, type_name, member, where=None):
        """The member's return type when it is a type with members, else None. A method that another
        package's CoC class adds makes that package a reference the caller needs."""
        returns = self.type_info(type_name)["methods"].get(member.lower())
        if returns is None:
            returns = self.extension_methods.get(type_name.lower(), {}).get(member.lower())
        if returns is None and self.type_info(type_name)["package"]:
            hit = self.added_methods(type_name).get(member.lower())
            if hit:
                returns = hit[2]
                if where:
                    self.added_needs.setdefault(hit[0], f"{where} calls {type_name}.{member}, which {hit[1]} adds")
        return returns if returns and self.find(returns, MEMBER_TYPE_KINDS) else None


def walk_code(index, where, this_type, source, named, called, forms):
    """Record the types and forms `source` names, and its method calls on types: (type, 'instance') for
    x.m(), (type, 'static', m) for T::m()."""
    code = strip_code(source)
    for name in NAMING_FUNCTIONS.findall(code):
        named.setdefault(name.lower(), (name, where))
    for name in FORM_FUNCTIONS.findall(code):
        forms.setdefault(name.lower(), (name, where))
    variables = {}
    parts = declaration_parts(signature(source))
    if parts:
        for type_name, param in [(parts[1], None)] + parts[2]:
            if index.find(type_name, SIGNATURE_TYPE_KINDS):
                named.setdefault(type_name.lower(), (type_name, where))
                if param:
                    variables[param.lower()] = type_name
    tokens = CODE_TOKEN.findall(code)
    for i in range(len(tokens) - 1):
        first, second = tokens[i], tokens[i + 1]
        third = tokens[i + 2] if i + 2 < len(tokens) else ""
        if (WORD.match(first) and WORD.match(second) and third in ("=", ";", ",", ")")
                and first.lower() not in NOT_TYPES and second.lower() not in NOT_TYPES
                and index.find(first, SIGNATURE_TYPE_KINDS)):
            named.setdefault(first.lower(), (first, where))
            variables[second.lower()] = first
        elif second == "::" and WORD.match(first) and index.find(first, SIGNATURE_TYPE_KINDS):
            named.setdefault(first.lower(), (first, where))
        elif first.lower() in ("new", "as", "is") and WORD.match(second) and index.find(second, SIGNATURE_TYPE_KINDS):
            named.setdefault(second.lower(), (second, where))
    i = 0
    while i < len(tokens):
        word = tokens[i].lower()
        current = None
        if i and tokens[i - 1] in (".", "::"):
            current = None
        elif word in ("this", "next"):
            current = this_type
            if word == "next" and this_type:
                called.setdefault((this_type.lower(), "instance"), (this_type, where, "next"))
        elif word in variables:
            current = variables[word]
        elif i + 1 < len(tokens) and tokens[i + 1] == "::" and index.find(tokens[i], MEMBER_TYPE_KINDS):
            current = tokens[i]
        j = i + 1
        while current and j + 1 < len(tokens) and tokens[j] in (".", "::") and WORD.match(tokens[j + 1]):
            if not (j + 2 < len(tokens) and tokens[j + 2] == "("):
                current, j = None, j + 2  # a field, or an enum value: loads nothing
                continue
            member = tokens[j + 1]
            key = (current.lower(), "instance") if tokens[j] == "." else (current.lower(), "static", member.lower())
            called.setdefault(key, (current, where, member))
            current, j = index.return_type(current, member, where), closing_paren(tokens, j + 2)
        i = j if j > i + 1 else i + 1


def code_uses(index, package_dir, model):
    """Walk every method in the model's own files. Returns (named, called, forms) as walk_code fills them."""
    sources = []
    for path in sorted(glob.glob(os.path.join(package_dir, model, "Ax*", "*.xml"))):
        code = safe_load(path).find("SourceCode")
        if code is None:
            continue
        owner = os.path.basename(path)[:-4]
        declaration = code.findtext("Declaration") or ""
        this_type = owner
        target = re.search(r"ExtensionOf\s*\(\s*(\w+)\s*\(\s*(\w+)", strip_code(declaration), re.IGNORECASE)
        if target:  # a CoC class: `this` is the target, unless it is a form, data source or control
            this_type = target.group(2) if target.group(1).lower() in ("tablestr", "classstr", "viewstr", "mapstr") else None
        methods = code.findall("Methods/Method")
        if target and this_type:
            for method in methods:
                parts = declaration_parts(signature(method.findtext("Source")))
                if parts:
                    index.extension_methods.setdefault(this_type.lower(), {})[parts[0].lower()] = parts[1]
        sources.append((owner, this_type, declaration))
        sources.extend((f"{owner}.{m.findtext('Name')}", this_type, m.findtext("Source") or "") for m in methods)
    named, called, forms = {}, {}, {}
    for where, this_type, source in sources:
        walk_code(index, where, this_type, source, named, called, forms)
    return named, called, forms


def form_view_needs(roots, index, form):
    """Enum packages behind the bound fields of a form's view data sources: the compiler resolves those
    when code names the form. A form extension without such code doesn't load it."""
    found, tables = {}, {}
    files = object_files(roots, KINDS["form"], form)
    for ds in safe_load(files[0]).findall("DataSources/AxFormDataSource") if files else []:
        view = index.find(ds.findtext("Table"), ("view",))
        if not view:
            continue
        root = safe_load(view[2])
        query = object_files(roots, KINDS["query"], root.findtext("Query")) if root.findtext("Query") else []
        aliases = {}
        for container in [root] + [safe_load(path) for path in query[:1]]:
            for source in container.iter():
                if source.tag.startswith("AxQuerySimple") and source.findtext("Name") and source.findtext("Table"):
                    aliases[source.findtext("Name").lower()] = source.findtext("Table")
        for field in root.findall("Fields/AxViewField"):
            table = index.find(aliases.get((field.findtext("DataSource") or "").lower()), ("table", "view"))
            if not table:
                continue
            if table[2] not in tables:
                tables[table[2]] = {(f.findtext("Name") or "").lower(): f.findtext("EnumType")
                                    for f in safe_load(table[2]).findall("Fields/AxTableField")}
            enum_name = tables[table[2]].get((field.findtext("DataField") or "").lower())
            enum = index.find(enum_name, ("enum",)) if enum_name else None
            if enum:
                found.setdefault(enum[1], f"form {form} data source {ds.findtext('Name')} (a view) field "
                                          f"{field.findtext('Name')} uses enum {enum_name}")
    return found


def predicted_needs(roots, index, package, named, called, forms):
    """Packages the compiler will ask for: types the code names, then what its calls and named forms load."""
    direct, loaded = {}, {}
    for needed, why in index.added_needs.items():
        if needed != package:
            direct.setdefault(needed, why)
    for _, (type_name, where) in sorted(named.items()):
        hit = index.find(type_name)
        if hit and hit[1] != package:
            direct.setdefault(hit[1], f"{where} uses {hit[0]} {type_name}")
    for key, (type_name, where, member) in sorted(called.items()):
        info = index.type_info(type_name)
        while info["package"] == package and info["base"]:  # the model's own class: its base's members
            info = index.type_info(info["base"])
        if not info["package"] or info["package"] == package:
            continue
        uses = info["instance"] if key[1] == "instance" else info["method"].get(key[2], {})
        call = f"{type_name} methods" if key[1] == "instance" else f"{type_name}::{member}"
        for needed, why in uses.items():
            loaded.setdefault(needed, f"{why}; {where} calls {call}")
    for _, (form, where) in sorted(forms.items()):
        for needed, why in form_view_needs(roots, index, form).items():
            loaded.setdefault(needed, f"{why}; {where} names the form")
    return direct, loaded


def log_needs(roots, logs, cache, index=None):
    """Packages a pac or xppc compile log says are missing."""
    needs = {}
    for log in logs:
        with open(log, "r", encoding="utf-8", errors="ignore") as handle:
            text = handle.read()
        for package in COMPILER_REFERENCE.findall(text):
            needs.setdefault(package, f"compiler: a reference to Dynamics.AX.{package} is required")
        for groups in COMPILER_MISSING_TYPE.findall(text):
            name = next(group for group in groups if group)
            package = package_of(roots, TYPE_KINDS, name, cache)
            if package:
                needs.setdefault(package, f"compiler: {name} not found; it is defined in {package}")
        for type_name, method in COMPILER_MISSING_METHOD.findall(text) if index else []:
            hit = index.added_methods(type_name).get(method.lower())
            if hit:
                needs.setdefault(hit[0], f"compiler: {type_name} has no method {method}; {hit[1]} in {hit[0]} adds it")
    return needs


def reference_cycle(include, start):
    """A cycle through `start` among the models under the --include folders, as a list of packages."""
    graph = {}
    for folder in include:
        for path in glob.glob(os.path.join(folder, "*", "Descriptor", "*.xml")):
            try:
                info = read_descriptor(path)
            except (ET.ParseError, OSError, UnicodeDecodeError):
                continue
            graph.setdefault(info["module"] or info["name"], set()).update(info["refs"])
    stack, seen = [(start, [start])], set()
    while stack:
        node, trail = stack.pop()
        for ref in graph.get(node, ()):
            if ref == start:
                return trail + [start]
            if ref in graph and ref not in seen:
                seen.add(ref)
                stack.append((ref, trail + [ref]))
    return None


def cmd_model(roots, args):
    if not args.include:
        raise LookupError_("model needs --include <root>/src so it can find the model's descriptor.")
    UNREADABLE.clear()
    descriptors = []
    for folder in args.include:
        descriptors.extend(glob.glob(os.path.join(folder, "*", "Descriptor", args.name + ".xml")))
    if not descriptors:
        return 1, [f"No descriptor for model {args.name} under --include (expected <Package>/Descriptor/{args.name}.xml)."]
    path = descriptors[0]
    package_dir = os.path.dirname(os.path.dirname(path))
    package = os.path.basename(package_dir)
    try:
        info = read_descriptor(path)
    except (ET.ParseError, OSError, UnicodeDecodeError) as error:
        return 1, [f"Can't read the descriptor {path}: {error}"]
    refs = set(info["refs"])
    errors, warnings = [], []

    if info["name"] != args.name:
        errors.append(f"descriptor Name is {info['name']!r}, file is {args.name}.xml")
    if info["module"] != package:
        errors.append(f"ModelModule is {info['module']!r}, but the package folder is {package}")
    if info["publisher"].lower() == "microsoft":
        warnings.append("Publisher is Microsoft (the pac package init default); pass --publisher <your company>")
    own_package = os.path.normcase(os.path.abspath(package_dir))
    clashes = set()
    for root in roots:
        for candidate in sorted({args.name, package}):
            other = os.path.join(root, candidate)
            if os.path.isdir(os.path.join(other, "Descriptor")) and os.path.normcase(os.path.abspath(other)) != own_package:
                clashes.add(f"package {candidate} ({os.path.relpath(other, root)})")
            for hit in glob.glob(os.path.join(root, "*", "Descriptor", candidate + ".xml")):
                if os.path.normcase(os.path.abspath(os.path.dirname(os.path.dirname(hit)))) != own_package:
                    clashes.add(f"model {candidate} ({os.path.relpath(os.path.dirname(os.path.dirname(hit)), root)})")
    errors.extend(f"{clash} already exists; choose a unique, prefixed name" for clash in sorted(clashes))
    for ref in sorted(refs):
        if ref == package:
            errors.append(f"the model references its own package {ref}")
        elif not any(os.path.isdir(os.path.join(root, ref, "Descriptor")) for root in roots):
            errors.append(f"reference {ref} is not a package in the SDK or --include folders")
    cycle = reference_cycle(args.include, package)
    if cycle:
        errors.append("circular references: " + " -> ".join(cycle))

    cache = {}
    needs, unresolved = model_needs(roots, package_dir, args.name, cache)
    index = TypeIndex(roots)
    named, called, forms = code_uses(index, package_dir, args.name)
    direct, loaded = predicted_needs(roots, index, package, named, called, forms)
    for needed, why in direct.items():
        needs.setdefault(needed, why)
    missing = {p: why for p, why in needs.items() if p != package and p not in refs}
    predicted = {p: why for p, why in loaded.items() if p != package and p not in refs and p not in missing}
    known = set(missing) | set(predicted)
    from_log = {p: why for p, why in log_needs(roots, args.compile_log, cache, index).items()
                if p != package and p not in refs and p not in known}

    rows = [f"model {args.name}: package {package}, publisher {info['publisher'] or '?'}, layer {info['layer'] or '?'}",
            f"references ({len(refs)}): {', '.join(info['refs']) or 'none'}"]
    rows.extend(f"error: {e}" for e in errors)
    rows.extend(f"warning: {w}" for w in warnings)
    used = sorted(p for p in needs if p != package)
    rows.append(f"packages its metadata uses directly ({len(used)}): {', '.join(used) or 'none'}")
    calls = sorted(p for p in loaded if p != package and p not in used)
    if calls:
        rows.append(f"packages its code's calls also need ({len(calls)}): {', '.join(calls)}")
    if missing:
        rows.append(f"add to ModuleReferences ({len(missing)}):")
        rows.extend(capped([f"  {p}: {why}" for p, why in sorted(missing.items())], args.limit, "use --limit"))
    if predicted:
        rows.append(f"add before compiling: packages the standard types this code calls into need ({len(predicted)}):")
        rows.extend(capped([f"  {p}: {why}" for p, why in sorted(predicted.items())], args.limit, "use --limit"))
    if args.compile_log:
        rows.append(f"add from the compile log ({len(from_log)}):" if from_log else "compile log: no missing references")
        rows.extend(capped([f"  {p}: {why}" for p, why in sorted(from_log.items())], args.limit, "use --limit"))
    if unresolved:
        rows.append("not found in any package (kernel types, or misspelled): "
                    + ", ".join(capped(sorted(unresolved, key=str.lower), args.limit, "use --limit")))
    if UNREADABLE:
        rows.append(f"warning: skipped {len(UNREADABLE)} files that could not be read: "
                    + "; ".join(capped(UNREADABLE, args.limit, "use --limit")))
    to_add = len(missing) + len(predicted) + len(from_log)
    problems = len(errors) + to_add
    plural = lambda count, word: f"{count} {word}" + ("" if count == 1 else "s")
    rows.append("result: " + ("OK" if not problems else
                              f"{plural(len(errors), 'error')}, {plural(to_add, 'reference')} to add"))
    return (1 if problems else 0), rows


# ---------------------------------------------------------------- entry point

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--sdk", help="PackagesLocalDirectory to read (default: the installed SDK)")
    common.add_argument("--version", help="SDK version when several are installed, e.g. 10.0.2790.83")
    common.add_argument("--include", action="append", default=[],
                        help="extra metadata root laid out <Package>/<Model>/Ax*/, such as the repo's src folder")
    common.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximum lines per list")

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("find", parents=[common], help="which package and model hold an object")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("name")
    p.set_defaults(run=cmd_find)

    p = sub.add_parser("members", parents=[common], help="method signatures")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("name")
    p.add_argument("--member", help="one method: signature, wrapping notes, wrapper signature")
    p.add_argument("--datasource", help="form only: a data source's overridden methods")
    p.add_argument("--field", help="form only, with --datasource: a data field's overridden methods")
    p.add_argument("--control", help="form only: a control's overridden methods")
    p.set_defaults(run=cmd_members)

    p = sub.add_parser("table", parents=[common], help="fields, field groups, indexes")
    p.add_argument("name")
    p.add_argument("--field", help="only fields whose name contains this text, with their field groups")
    p.set_defaults(run=cmd_table)

    p = sub.add_parser("form", parents=[common], help="pattern, data sources, controls")
    p.add_argument("name")
    p.add_argument("--control", help="only controls whose name contains this text")
    p.add_argument("--parent", help="only the controls directly under this control, such as a grid's columns")
    p.add_argument("--depth", type=int, default=2, help="control tree depth without --control or --parent")
    p.set_defaults(run=cmd_form)

    p = sub.add_parser("extensions", parents=[common], help="extension files and CoC or handler classes")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("name")
    p.add_argument("--all", action="store_true", help="scan every class file, not only names containing the target")
    p.set_defaults(run=cmd_extensions)

    p = sub.add_parser("model", parents=[common], help="check a model's descriptor and the references it needs")
    p.add_argument("name", help="the model; its descriptor is found under the --include folders")
    p.add_argument("--compile-log", action="append", default=[],
                   help="a pac or xppc log; packages it says are missing are reported too")
    p.set_defaults(run=cmd_model)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        roots = resolve_roots(args.sdk, args.version, args.include)
        code, rows = args.run(roots, args)
    except LookupError_ as problem:
        print(problem, file=sys.stderr)
        return 2
    except ET.ParseError as problem:
        print(f"Could not parse an AOT file: {problem}", file=sys.stderr)
        return 2
    print("\n".join(rows))
    return code


if __name__ == "__main__":
    sys.exit(main())
