from pdf_toolkit.convert import ConvertOptions, build_kwargs


def test_rag_profile_defaults():
    kw = build_kwargs(ConvertOptions(profile="rag"))
    assert kw["format"] == "markdown,json"
    assert kw["image_output"] == "external"
    assert kw["sanitize"] is True
    assert "hybrid" not in kw


def test_structured_profile_uses_struct_tree():
    kw = build_kwargs(ConvertOptions(profile="structured"))
    assert kw["format"] == "json"
    assert kw["use_struct_tree"] is True


def test_review_profile_requests_annotated_pdf():
    kw = build_kwargs(ConvertOptions(profile="review"))
    assert "pdf" in kw["format"].split(",")
    assert "json" in kw["format"].split(",")


def test_ocr_enables_hybrid():
    kw = build_kwargs(
        ConvertOptions(profile="rag", ocr=True, hybrid_full=True, hybrid_url="http://h:5002")
    )
    assert kw["hybrid"] == "docling-fast"
    assert kw["hybrid_mode"] == "full"
    assert kw["hybrid_url"] == "http://h:5002"


def test_hybrid_url_alone_activates_hybrid():
    kw = build_kwargs(ConvertOptions(profile="rag", hybrid_url="http://sidecar:5002"))
    assert kw["hybrid"] == "docling-fast"
    assert kw["hybrid_url"] == "http://sidecar:5002"


def test_sanitize_disabled_propagates():
    kw = build_kwargs(ConvertOptions(sanitize=False))
    assert kw["sanitize"] is False


def test_extra_overrides_profile():
    kw = build_kwargs(ConvertOptions(profile="rag", extra={"format": "text"}))
    assert kw["format"] == "text"
