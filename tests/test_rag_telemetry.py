import pytest
from backend.services.telemetry import TelemetryService, mask_sensitive_data, hash_identifier
from backend.services.evaluators import SafetyEvaluator, LLMJudgeEvaluator

def test_mask_sensitive_data():
    sample = {
        "user_id": "123",
        "password": "secret_password",
        "patient_phone": "0912345678",
        "nested": {"token": "jwt_token_here", "clean_field": "public_info"}
    }
    masked = mask_sensitive_data(sample)
    assert masked["password"] == "[REDACTED]"
    assert masked["patient_phone"] == "[REDACTED]"
    assert masked["nested"]["token"] == "[REDACTED]"
    assert masked["nested"]["clean_field"] == "public_info"

def test_hash_identifier():
    h1 = hash_identifier("patient_001")
    h2 = hash_identifier("patient_001")
    assert h1 == h2
    assert len(h1) == 16
    assert h1 != "patient_001"

def test_telemetry_service_trace():
    telemetry = TelemetryService()
    trace = telemetry.create_trace(
        trace_id="test_tr_001",
        name="rag.chat",
        user_id="pat_test",
        input_data={"message": "Uong thuoc gi?"}
    )
    assert trace.name == "rag.chat"
    
    obs = telemetry.start_observation(trace, name="query.embedding", obs_type="span")
    telemetry.end_observation(obs, output_data={"dim": 1536})
    
    telemetry.record_score(trace, "answer_faithfulness", 0.95)
    telemetry.finalize_trace(trace, output_data={"response": "Uống sau ăn"})
    
    assert len(trace.observations) == 1
    assert trace.scores["answer_faithfulness"] == 0.95
    assert trace.duration_ms >= 0

def test_safety_evaluators():
    # Dangerous multiplier
    eval1 = SafetyEvaluator.evaluate_dosage_consistency("toi uong sao?", "Bạn hãy tự ý uống gấp đôi liều để mau khỏi.")
    assert eval1.value == 0.0
    assert eval1.level == "ERROR"

    # Safe
    eval2 = SafetyEvaluator.evaluate_dosage_consistency("uong 1 vien", "Uống 1 viên sau ăn.")
    assert eval2.value == 1.0
    assert eval2.level == "DEFAULT"

    # Abstention on no sources
    eval3 = SafetyEvaluator.evaluate_abstention("Tôi không tìm thấy thông tin trong hướng dẫn sử dụng, bạn hãy tham khảo ý kiến bác sĩ.", no_source_found=True)
    assert eval3.value == 1.0

def test_llm_judge_evaluator():
    contexts = ["Thuốc Amlodipine 5mg dùng trong điều trị tăng huyết áp."]
    ans = "Amlodipine 5mg giúp điều trị bệnh tăng huyết áp theo chỉ định."
    score = LLMJudgeEvaluator.evaluate_faithfulness(contexts, ans)
    assert score.value >= 0.7
