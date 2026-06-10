from miniapp_ui_auto.ai.failure_analyzer import classify_failure


def test_classify_connection_reset_as_device_poco_issue():
    category, summary = classify_failure(
        [
            "Connection broken: ConnectionResetError(10054, '远程主机强迫关闭了一个现有的连接。')",
        ]
    )

    assert category == "设备/Poco连接问题"
    assert "Poco" in summary


def test_classify_empty_poco_response_as_device_poco_issue():
    category, summary = classify_failure(["Expecting value: line 1 column 1 (char 0)"])

    assert category == "设备/Poco连接问题"
    assert "Poco" in summary
