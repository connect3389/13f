from __future__ import annotations

import os
import re
import time
from typing import Any
from xml.etree import ElementTree as ET

import requests

from thirteenf import PARSER_VERSION
from thirteenf.envload import load_dotenv_if_present

SEC_DATA_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
SEC_ARCHIVE_TMPL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nd}/{primary}"


def _default_headers(host: str) -> dict[str, str]:
    load_dotenv_if_present()
    ua = os.environ.get(
        "THIRTEENF_SEC_USER_AGENT",
        "thirteenf/0.1 (educational research; respectful low-volume requests)",
    )
    if host == "www.sec.gov":
        return {
            "User-Agent": ua,
            "Accept": "application/xml,text/xml,application/xhtml+xml,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.sec.gov/",
        }
    return {
        "User-Agent": ua,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }


def _sleep_polite() -> None:
    time.sleep(float(os.environ.get("THIRTEENF_SEC_DELAY", "0.12")))


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def fetch_submissions(cik10: str) -> dict[str, Any]:
    url = SEC_DATA_SUBMISSIONS.format(cik10=cik10)
    r = requests.get(url, headers=_default_headers("data.sec.gov"), timeout=60)
    r.raise_for_status()
    _sleep_polite()
    return r.json()


def iter_13f_filings(submissions: dict[str, Any], cik10: str) -> list[dict[str, Any]]:
    """该 CIK 的 submissions JSON 中 filings.recent 里的全部 13F-HR(/A)。

    不以 accession 首段过滤：部分机构首份 13F 的 accession 前缀与 CIK 不同
    （例如 0002045724 的 2024-12-31 期为 0000935836-25-000120），但仍在该公司
    submissions 列表中。更早历史在 filings.files 分页，需另行拉取（当前未实现）。
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    out: list[dict[str, Any]] = []
    n = len(forms)
    keys = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "primaryDocument",
        "primaryDocDescription",
    )
    arrays = {k: recent.get(k, []) for k in keys}
    for i in range(n):
        form = forms[i]
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        acc = arrays["accessionNumber"][i] if i < len(arrays["accessionNumber"]) else None
        if not acc:
            continue
        fd = {k: arrays[k][i] if i < len(arrays[k]) else None for k in keys}
        fd["form"] = form
        fd["is_amendment"] = form.endswith("/A")
        fd["accessionNumber"] = acc
        out.append(fd)
    return out


def accession_to_nd(acc: str) -> str:
    return acc.replace("-", "")


def archive_url(cik10: str, accession: str, primary: str) -> str:
    cik_int = str(int(cik10))
    acc_nd = accession_to_nd(accession)
    return SEC_ARCHIVE_TMPL.format(cik_int=cik_int, accession_nd=acc_nd, primary=primary)


def fetch_primary_doc(url: str) -> bytes:
    r = requests.get(url, headers=_default_headers("www.sec.gov"), timeout=120)
    r.raise_for_status()
    _sleep_polite()
    body = r.content
    head = body[:12000].decode("utf-8", errors="ignore")
    if "Undeclared Automated Tool" in head or "declare your traffic" in head.lower():
        raise RuntimeError(
            "SEC 返回了「未声明自动化访问」拦截页（HTML），不是 13F XML。"
            "请在同一终端先设置符合 SEC 要求的 User-Agent（需含可联系的姓名/机构与邮箱），例如：\n"
            "  export THIRTEENF_SEC_USER_AGENT='Your Name your.email@example.com'\n"
            "说明见 https://www.sec.gov/developer"
        )
    if body.strip().startswith(b"<!DOCTYPE html") or b"<html" in body[:2000].lower():
        if b"informationtable" not in body.lower() and b"infotable" not in body.lower():
            raise RuntimeError(
                "期望为 13F/XML，但响应看起来像 HTML 且不包含 informationTable。"
                "若为 SEC 拦截页，请按上文设置 THIRTEENF_SEC_USER_AGENT 后重试。"
            )
    return body


def _root_from_content(content: bytes) -> tuple[ET.Element | None, list[str]]:
    """先严格解析；失败后尝试把 <infoTable> 片段拼成合法 XML（应对 XSL 外壳等劣构文档）。"""
    warnings: list[str] = []
    try:
        return ET.fromstring(content), warnings
    except ET.ParseError as e:
        warnings.append(f"XML strict parse failed: {e}")
    text = content.decode("utf-8", errors="replace")
    # primary 常为劣构 XML；SEC 常见带前缀标签如 <ns1:infoTable>（原正则只匹配无前缀的 infoTable）
    blocks = re.findall(
        r"<(?:[\w.-]+:)?infoTable\b[^>]*>.*?</(?:[\w.-]+:)?infoTable>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not blocks:
        warnings.append("regex: no <infoTable>...</infoTable> fragments")
        return None, warnings
    wrapped = "<informationTable>" + "".join(blocks) + "</informationTable>"
    try:
        return ET.fromstring(wrapped), warnings
    except ET.ParseError as e:
        warnings.append(f"fragment bundle parse failed: {e}")
        return None, warnings


def parse_information_table_xml(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse 13F informationTable XML into row dicts.
    Value field: 历史多为「千美元」，近年部分 filer（如 Berkshire）为「美元」；入库后由
    ``value_scale.infer_multiplier_from_parsed_rows`` 写入 ``ingest_record.value_usd_multiplier``。
    """
    warnings: list[str] = []
    root, w0 = _root_from_content(content)
    warnings.extend(w0)
    if root is None:
        if b"informationTable" not in content.lower() and b"infotable" not in content.lower():
            warnings.append("no infoTable-like content in body")
        return [], warnings
    rows: list[dict[str, Any]] = []
    line_no = 0
    for el in root.iter():
        if _local_name(el.tag) != "infoTable":
            continue
        line_no += 1
        row: dict[str, Any] = {"line_no": line_no}
        for child in el:
            name = _local_name(child.tag)
            text = (child.text or "").strip()
            if name in (
                "nameOfIssuer",
                "titleOfClass",
                "cusip",
                "figi",
                "putCall",
                "investmentDiscretion",
                "otherManager",
            ):
                row[name] = text
            elif name == "value":
                try:
                    row["value"] = float(text.replace(",", ""))
                except ValueError:
                    row["value"] = None
                    warnings.append(f"line {line_no}: bad value {text!r}")
            elif name in ("sshPrnamt", "shrsOrPrnAmt"):
                subs = list(child)
                if subs:
                    for sub in subs:
                        sn = _local_name(sub.tag)
                        st = (sub.text or "").strip()
                        if sn == "sshPrnamtType":
                            row["sshPrnamtType"] = st
                        elif sn == "sshPrnamt":
                            try:
                                row["shares"] = float(st.replace(",", ""))
                            except ValueError:
                                row["shares"] = None
                else:
                    try:
                        row["shares"] = float(text.replace(",", ""))
                    except ValueError:
                        row["shares"] = None
        if "shares" not in row:
            for child in el:
                if _local_name(child.tag) == "sshPrnamt" and not list(child):
                    t = (child.text or "").strip()
                    try:
                        row["shares"] = float(t.replace(",", ""))
                    except ValueError:
                        pass
        rows.append(row)
    if not rows:
        warnings.append("parsed XML but zero infoTable rows")
    return rows, warnings


def companion_infotable_urls(primary_document_url: str) -> list[str]:
    """primary 常在 xslForm13F_*/primary_doc.xml，同目录常有 infotable.xml。"""
    parts = primary_document_url.rsplit("/", 1)
    if len(parts) != 2:
        return []
    base_dir, _ = parts
    two_up = primary_document_url.rsplit("/", 2)[0]
    names = ("infotable.xml", "Infotable.xml", "informationtable.xml")
    out: list[str] = []
    for n in names:
        out.append(f"{base_dir}/{n}")
    for n in names:
        out.append(f"{two_up}/{n}")
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def filing_directory_base_url(cik10: str, accession: str) -> str:
    cik_int = str(int(cik10))
    acc_nd = accession_to_nd(accession)
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nd}"


def auxiliary_xml_urls_from_filing_index(cik10: str, accession: str) -> tuple[list[str], list[str]]:
    """
    新版 EDGAR 目录提供 index.json。primary_doc.xml 常仅为封面 HTML，
    持仓多在另一份 *.xml（名称因机构而异，如 SALP_13FQ425.xml）。
    """
    warns: list[str] = []
    idx_url = f"{filing_directory_base_url(cik10, accession)}/index.json"
    try:
        r = requests.get(idx_url, headers=_default_headers("www.sec.gov"), timeout=60)
        r.raise_for_status()
        _sleep_polite()
        data = r.json()
    except Exception as e:
        return [], [f"index.json fetch/parse: {e}"]
    items = data.get("directory", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    base = filing_directory_base_url(cik10, accession)
    candidates: list[tuple[int, str]] = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name.lower().endswith(".xml"):
            continue
        if name == "primary_doc.xml":
            continue
        sz_raw = it.get("size")
        try:
            sz = int(str(sz_raw).strip() or "0")
        except ValueError:
            sz = 0
        candidates.append((sz, f"{base}/{name}"))
    candidates.sort(key=lambda x: -x[0])
    return [u for _, u in candidates], warns


def resolve_edgar_xml_url(cik10: str, filing: dict[str, Any]) -> str | None:
    primary = filing.get("primaryDocument")
    accession = filing.get("accessionNumber")
    if not primary or not accession:
        return None
    return archive_url(cik10, accession, primary)


def try_parse_or_find_infotable(
    cik10: str,
    filing: dict[str, Any],
    primary_bytes: bytes,
    *,
    primary_url: str | None = None,
) -> tuple[bytes, list[dict[str, Any]], list[str]]:
    """解析 primary；若无行则读 index.json 找其它 XML，再尝试固定 infotable 路径与 href。"""
    rows, warns = parse_information_table_xml(primary_bytes)
    if rows:
        return primary_bytes, rows, warns
    acc = filing.get("accessionNumber") or ""
    if acc:
        aux_urls, w_idx = auxiliary_xml_urls_from_filing_index(cik10, acc)
        warns.extend(w_idx)
        for alt in aux_urls:
            try:
                body = fetch_primary_doc(alt)
                r2, w2 = parse_information_table_xml(body)
                if r2:
                    return body, r2, warns + w2 + [f"used index.json xml {alt}"]
                warns.extend(w2)
            except (requests.HTTPError, OSError, RuntimeError) as e:
                warns.append(f"{alt}: {e}")
    if primary_url:
        for alt in companion_infotable_urls(primary_url):
            try:
                body = fetch_primary_doc(alt)
                r2, w2 = parse_information_table_xml(body)
                if r2:
                    return body, r2, warns + w2 + [f"used companion file {alt}"]
                warns.extend(w2)
            except (requests.HTTPError, OSError, RuntimeError) as e:
                warns.append(f"{alt}: {e}")
    text = primary_bytes.decode("utf-8", errors="ignore")
    m = re.search(
        r'href=["\']([^"\']*infotable[^"\']*\.xml)["\']',
        text,
        re.I,
    )
    if m:
        rel = m.group(1).split("/")[-1]
        acc = filing.get("accessionNumber") or ""
        acc_nd = accession_to_nd(acc)
        cik_int = str(int(cik10))
        secondary = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nd}/{rel}"
        try:
            body = fetch_primary_doc(secondary)
            r2, w2 = parse_information_table_xml(body)
            if r2:
                return body, r2, warns + w2 + [f"followed href infotable {rel}"]
            warns.extend(w2)
        except (requests.HTTPError, OSError, RuntimeError) as e:
            warns.append(f"href secondary failed: {e}")
    return primary_bytes, [], warns + ["could not get holdings from primary or companions"]
