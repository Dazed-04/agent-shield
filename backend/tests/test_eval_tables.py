from evaluation.report import build_report
from evaluation.tables import render_csv, render_latex_ablation, render_markdown
from tests.test_eval_report import META, sample_rows


def test_tables_render_from_a_report():
    rep = build_report(sample_rows(), META, calibrated={"combined": 5.0}, n_boot=10)
    md = render_markdown(rep)
    assert "| Combined (risk engine) |" in md and "Highest-scoring false positives" in md and "Missed attacks" in md
    assert len(render_csv(rep).splitlines()) > 20
    tex = render_latex_ablation(rep)
    assert tex.count(r"\\") >= 4 and "_" not in tex.replace(r"\_", "")
