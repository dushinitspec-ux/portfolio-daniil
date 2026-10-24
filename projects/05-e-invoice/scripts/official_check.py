"""Cross-checks the generated XML with the official artefacts (a development tool, not a test).

For every bundled sample it converts the PDF with the offline extractor, then:
1. validates the XML against the OASIS UBL 2.1 Invoice schema (XSD, with lxml);
2. runs the CEN EN 16931 UBL schematron (ConnectingEurope, validation-1.3.17);
3. runs the KoSIT XRechnung UBL schematron (v2.6.0, XRechnung 3.0.2 bundle).
The schematron files are compiled XSLT 2.0, so they run on Saxon-HE (saxonche from PyPI).
The official KoSIT validator (Java) wraps the same three steps; it is not used here.

    uv run --group official python scripts/official_check.py

The artefacts are downloaded once into .cache/official/ (about 6 MB, not committed).
"""

import asyncio
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from saxonche import PySaxonProcessor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.extract.rules import RuleBasedExtractor  # noqa: E402
from app.pipeline import convert  # noqa: E402

CACHE = ROOT / ".cache" / "official"
UBL_BASE = "https://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/"
UBL_FILES = [
    "maindoc/UBL-Invoice-2.1.xsd",
    "common/UBL-CommonAggregateComponents-2.1.xsd",
    "common/UBL-CommonBasicComponents-2.1.xsd",
    "common/UBL-CommonExtensionComponents-2.1.xsd",
    "common/UBL-ExtensionContentDataType-2.1.xsd",
    "common/UBL-QualifiedDataTypes-2.1.xsd",
    "common/UBL-UnqualifiedDataTypes-2.1.xsd",
    "common/CCTS_CCT_SchemaModule-2.1.xsd",
    "common/UBL-CommonSignatureComponents-2.1.xsd",
    "common/UBL-SignatureAggregateComponents-2.1.xsd",
    "common/UBL-SignatureBasicComponents-2.1.xsd",
    "common/UBL-XAdESv132-2.1.xsd",
    "common/UBL-XAdESv141-2.1.xsd",
    "common/UBL-xmldsig-core-schema-2.1.xsd",
]
CEN_ZIP = (
    "https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/download/"
    "validation-1.3.17/en16931-ubl-1.3.17.zip"
)
CEN_XSLT = "xslt/EN16931-UBL-validation.xslt"
KOSIT_ZIP = (
    "https://github.com/itplr-kosit/xrechnung-schematron/releases/download/"
    "v2.6.0/xrechnung-3.0.2-schematron-2.6.0.zip"
)
KOSIT_XSLT = "schematron/ubl/XRechnung-UBL-validation.xsl"
# An official XRechnung example from the KoSIT test suite: a control that must pass.
KOSIT_EXAMPLE = (
    "https://raw.githubusercontent.com/itplr-kosit/xrechnung-testsuite/master/"
    "src/test/business-cases/standard/01.01a-INVOICE_ubl.xml"
)
SVRL = {"svrl": "http://purl.oclc.org/dsdl/svrl"}


def download(url: str, target: Path) -> Path:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as response:  # fixed, trusted URLs
            target.write_bytes(response.read())
    return target


def unpack(url: str, member: str, folder: str) -> Path:
    archive = download(url, CACHE / f"{folder}.zip")
    target = CACHE / folder / member
    if not target.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extract(member, CACHE / folder)
    return target


@dataclass
class Finding:
    flag: str
    rule_id: str
    text: str


def schematron(proc: PySaxonProcessor, xslt: Path, xml_file: Path) -> list[Finding]:
    compiler = proc.new_xslt30_processor()
    executable = compiler.compile_stylesheet(stylesheet_file=str(xslt))
    report = executable.transform_to_string(source_file=str(xml_file))
    root = etree.fromstring(report.encode("utf-8"))
    findings = []
    for node in root.iterfind(".//svrl:failed-assert", SVRL):
        text = " ".join("".join(node.itertext()).split())
        findings.append(Finding(node.get("flag", "?"), node.get("id", "?"), text[:140]))
    return findings


def main() -> int:
    for name in UBL_FILES:
        download(UBL_BASE + name, CACHE / "ubl-2.1" / name)
    schema = etree.XMLSchema(etree.parse(str(CACHE / "ubl-2.1" / "maindoc/UBL-Invoice-2.1.xsd")))
    cen = unpack(CEN_ZIP, CEN_XSLT, "en16931-ubl-1.3.17")
    kosit = unpack(KOSIT_ZIP, KOSIT_XSLT, "xrechnung-schematron-2.6.0")
    control = download(KOSIT_EXAMPLE, CACHE / "kosit-01.01a-INVOICE_ubl.xml")

    out = CACHE / "generated"
    out.mkdir(parents=True, exist_ok=True)
    documents = [("KoSIT example 01.01a (control)", control)]
    for pdf in sorted((ROOT / "samples").glob("*.pdf")):
        conversion = asyncio.run(convert(pdf.read_bytes(), RuleBasedExtractor(), pdf.name))
        target = out / f"{pdf.stem}.xml"
        target.write_bytes(conversion.xml)
        ours = ", ".join(r.id for r in conversion.report.errors) or "none"
        documents.append((f"{pdf.name} (this app's fatal rules: {ours})", target))

    with PySaxonProcessor(license=False) as proc:
        for title, path in documents:
            print(f"\n== {title}")
            doc = etree.parse(str(path))
            xsd = "valid" if schema.validate(doc) else f"INVALID: {schema.error_log.last_error}"
            print(f"   UBL 2.1 XSD: {xsd}")
            for label, xslt in (("CEN EN 16931", cen), ("KoSIT XRechnung", kosit)):
                findings = schematron(proc, xslt, path)
                fatal = [f for f in findings if f.flag == "fatal"]
                other = [f for f in findings if f.flag != "fatal"]
                print(f"   {label}: {len(fatal)} fatal, {len(other)} warning/information")
                for f in findings:
                    print(f"      [{f.flag}] {f.rule_id}: {f.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
