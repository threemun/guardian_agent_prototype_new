# voice_lab 接入 Guardian night-turn

这个脚本把电脑端语音模块接到 Guardian Agent：

```text
voice_lab 录音/STT
  -> POST /api/v1/guardian/conversations/night-turn
  -> Guardian 状态机
  -> reply_text
  -> voice_lab TTS 播放
```

## 前置条件

1. Guardian Web 服务已启动：

```powershell
cd "C:\Users\Wu Ting\Documents\Codex\2026-07-08\app-app\work\guardian_agent"
python .\server.py
```

2. `voice_lab 1.3.zip` 已解压，目录内能看到 `voice_lab.py`。

默认查找目录：

```text
C:\Users\Wu Ting\Desktop\物联网\agent开发\voice_lab
```

如果解压到别的位置，用 `--voice-lab-dir` 指定。

## 先用文字模式验证

先触发一个离床事件，然后不用麦克风，直接发送文本：

```powershell
python .\integrations\guardian_voice_bridge.py text "我去趟卫生间，不用担心" --elder-id E001
```

危险表达测试：

```powershell
python .\integrations\guardian_voice_bridge.py text "我没事，就是有点头晕" --elder-id E001
```

## 麦克风语音闭环

```powershell
python .\integrations\guardian_voice_bridge.py voice --elder-id E001
```

流程：

```text
1. 电脑播报：检测到您已离床，需要帮助吗？
2. 你对麦克风回答
3. 3 秒静音后停止收音
4. STT 得到文字
5. 文字发送给 Guardian night-turn
6. Agent 返回 reply_text
7. TTS 播放 reply_text
```
