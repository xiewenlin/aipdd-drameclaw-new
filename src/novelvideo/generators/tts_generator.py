"""TTS 语音合成模块。

使用 Edge TTS 生成中文语音。
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from novelvideo.task_backend.cancel import TaskCancelled, TaskTimedOut
from novelvideo.task_backend.subprocesses import run_project_subprocess


class TTSParams(BaseModel):
    """TTS 参数。"""

    text: str
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


class TTSResult(BaseModel):
    """TTS 生成结果。"""

    success: bool
    audio_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None


class VoiceInfo(BaseModel):
    """语音信息。"""

    name: str
    short_name: str
    gender: str
    locale: str


# 推荐的中文语音
RECOMMENDED_VOICES = {
    # 女声
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",  # 活泼女声（默认）
    "xiaoyi": "zh-CN-XiaoyiNeural",  # 温柔女声
    "xiaoxuan": "zh-CN-XiaoxuanNeural",  # 知性女声
    "xiaomo": "zh-CN-XiaomoNeural",  # 成熟女声
    "xiaorui": "zh-CN-XiaoruiNeural",  # 儿童女声
    "xiaoshuang": "zh-CN-XiaoshuangNeural",  # 可爱女声
    # 男声
    "yunxi": "zh-CN-YunxiNeural",  # 成熟男声
    "yunjian": "zh-CN-YunjianNeural",  # 解说男声
    "yunyang": "zh-CN-YunyangNeural",  # 新闻男声
    "yunhao": "zh-CN-YunhaoNeural",  # 广告男声
}


class EdgeTTSGenerator:
    """Edge TTS 语音生成器。

    使用微软 Edge TTS 服务生成高质量中文语音。

    示例:
        >>> generator = EdgeTTSGenerator()
        >>> result = await generator.generate(
        ...     text="这是一段测试文本",
        ...     output_path="output/audio.mp3"
        ... )
    """

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ):
        """初始化生成器。

        Args:
            voice: 语音名称，默认从配置读取
            rate: 语速调整（如 "+10%", "-5%"）
            pitch: 音调调整（如 "+5Hz", "-10Hz"）
        """
        self.voice = voice or "zh-CN-XiaoxiaoNeural"
        self.rate = rate or "+0%"
        self.pitch = pitch or "+0Hz"

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        generate_subtitle: bool = True,
        **kwargs,
    ) -> TTSResult:
        """生成语音。

        Args:
            text: 要合成的文本
            output_path: 输出音频路径（.mp3）
            voice: 语音名称（覆盖默认值）
            rate: 语速调整
            pitch: 音调调整
            generate_subtitle: 是否生成字幕文件

        Returns:
            生成结果
        """
        try:
            import edge_tts
        except ImportError:
            return TTSResult(
                success=False,
                error="edge-tts not installed. Run: pip install edge-tts",
            )

        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 使用参数或默认值
            use_voice = voice or self.voice
            use_rate = rate or self.rate
            use_pitch = pitch or self.pitch

            # 创建通信对象
            communicate = edge_tts.Communicate(
                text,
                use_voice,
                rate=use_rate,
                pitch=use_pitch,
            )

            # 生成音频
            subtitle_path = None
            if generate_subtitle:
                subtitle_path = output_path.rsplit(".", 1)[0] + ".srt"
                submaker = edge_tts.SubMaker()

                with open(output_path, "wb") as audio_file:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            audio_file.write(chunk["data"])
                        elif chunk["type"] == "SentenceBoundary":
                            # edge-tts 7.x uses SentenceBoundary and feed()
                            submaker.feed(chunk)

                # 保存字幕（SRT 格式）
                srt_content = submaker.get_srt()
                if srt_content:
                    with open(subtitle_path, "w", encoding="utf-8") as sub_file:
                        sub_file.write(srt_content)
            else:
                await communicate.save(output_path)

            # 获取音频时长
            duration = await self._get_audio_duration(output_path)

            return TTSResult(
                success=True,
                audio_path=output_path,
                subtitle_path=subtitle_path,
                duration_seconds=duration,
            )

        except (TaskCancelled, TaskTimedOut):
            raise
        except Exception as e:
            return TTSResult(
                success=False,
                error=str(e),
            )

    async def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长。"""
        try:
            result = run_project_subprocess(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return float(result.stdout.strip())
        except (TaskCancelled, TaskTimedOut):
            raise
        except Exception:
            # 估算：中文约 3 字/秒
            return 0.0

    async def generate_batch(
        self,
        texts: list[str],
        output_dir: str,
        filename_prefix: str = "audio",
    ) -> list[TTSResult]:
        """批量生成语音。

        Args:
            texts: 文本列表
            output_dir: 输出目录
            filename_prefix: 文件名前缀

        Returns:
            生成结果列表
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for i, text in enumerate(texts):
            output_path = os.path.join(output_dir, f"{filename_prefix}_{i + 1:03d}.mp3")
            result = await self.generate(text, output_path)
            results.append(result)

        return results

    async def list_voices(self, locale: str = "zh-CN") -> list[VoiceInfo]:
        """列出可用语音。

        Args:
            locale: 语言区域代码

        Returns:
            语音信息列表
        """
        try:
            import edge_tts

            voices = await edge_tts.list_voices()
            result = []

            for voice in voices:
                if voice["Locale"].startswith(locale):
                    result.append(
                        VoiceInfo(
                            name=voice["FriendlyName"],
                            short_name=voice["ShortName"],
                            gender=voice["Gender"],
                            locale=voice["Locale"],
                        )
                    )

            return result
        except Exception:
            return []


class CosyVoiceTTSGenerator:
    """阿里云 CosyVoice TTS 生成器。

    使用 DashScope SDK 调用 CosyVoice 模型生成高质量中文语音。

    示例:
        >>> generator = CosyVoiceTTSGenerator()
        >>> result = await generator.generate(
        ...     text="这是一段测试文本",
        ...     output_path="output/audio.mp3"
        ... )
    """

    def __init__(
        self,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
        speech_rate: Optional[float] = None,
    ):
        """初始化生成器（通过 NewAPI 实现）。

        Args:
            model: 模型名称，默认从 NewAPI 配置读取
            voice: 音色名称，默认从配置读取
            api_key: API Key，默认从 NewAPI 配置读取
            speech_rate: 语速倍率 [0.5, 2.0]，默认从配置读取
        """
        from novelvideo.model_catalog import model_runtime_resolver

        resolved = model_runtime_resolver.resolve("character_tts")
        self.model = model or resolved.model_id
        self.base_url = resolved.base_url.rstrip("/")
        self.voice = voice or "longxiaoxia_v3"
        self.api_key = api_key or resolved.api_key
        self.speech_rate = speech_rate or 1.2

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        generate_subtitle: bool = True,
        speech_rate: Optional[float] = None,
        **kwargs,
    ) -> TTSResult:
        """生成语音。

        Args:
            text: 要合成的文本
            output_path: 输出音频路径（.mp3）
            voice: 音色名称（覆盖默认值）
            generate_subtitle: 是否生成字幕文件（CosyVoice 暂不支持）
            speech_rate: 语速倍率（覆盖默认值，用于 dialogue beat）

        Returns:
            生成结果
        """
        try:
            import aiohttp
        except ImportError:
            return TTSResult(
                success=False,
                error="aiohttp not installed. Run: pip install aiohttp",
            )

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            use_voice = voice or self.voice
            use_speech_rate = speech_rate if speech_rate is not None else self.speech_rate

            # OpenAI 兼容 TTS API 格式：POST {base_url}/v1/audio/speech
            url = f"{self.base_url}/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "input": text,
                "voice": use_voice,
                "response_format": "mp3",
                "speed": use_speech_rate,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status < 200 or resp.status >= 300:
                        error_text = await resp.text()
                        return TTSResult(
                            success=False,
                            error=f"NewAPI TTS failed: HTTP {resp.status} - {error_text}",
                        )

                    # 写入音频文件
                    with open(output_path, "wb") as f:
                        f.write(await resp.read())

            # 验证文件
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return TTSResult(
                    success=False,
                    error="TTS generated empty file",
                )

            return TTSResult(
                success=True,
                audio_path=output_path,
                duration_seconds=0.0,
            )

        except (TaskCancelled, TaskTimedOut):
            raise
        except Exception as exc:
            return TTSResult(
                success=False,
                error=str(exc),
            )

    async def generate_batch(
        self,
        texts: list[str],
        output_dir: str,
        filename_prefix: str = "audio",
    ) -> list[TTSResult]:
        """批量生成语音。

        Args:
            texts: 文本列表
            output_dir: 输出目录
            filename_prefix: 文件名前缀

        Returns:
            生成结果列表
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for i, text in enumerate(texts):
            output_path = os.path.join(output_dir, f"{filename_prefix}_{i + 1:03d}.mp3")
            result = await self.generate(text, output_path)
            results.append(result)

        return results


class MockTTSGenerator:
    """模拟 TTS 生成器（用于测试）。

    不调用真实 API，生成空音频文件。
    """

    def __init__(self):
        self.voice = "mock-voice"

    async def generate(
        self,
        text: str,
        output_path: str,
        **kwargs,
    ) -> TTSResult:
        """生成模拟音频。"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 估算时长（中文约 3 字/秒）
            duration = len(text) / 3.0

            # 创建一个简单的静音 MP3（用 ffmpeg）
            try:
                import subprocess

                run_project_subprocess(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"anullsrc=r=44100:cl=stereo",
                        "-t",
                        str(duration),
                        "-acodec",
                        "libmp3lame",
                        output_path,
                    ],
                    capture_output=True,
                    check=True,
                    timeout=30 * 60,
                )
            except (TaskCancelled, TaskTimedOut):
                raise
            except Exception:
                # 如果 ffmpeg 不可用，创建空文件
                with open(output_path, "wb") as f:
                    f.write(b"")

            # 创建字幕文件（SRT 格式）
            subtitle_path = output_path.rsplit(".", 1)[0] + ".srt"
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write("1\n")
                f.write(f"00:00:00,000 --> 00:00:{int(duration):02d},000\n")
                f.write(text[:100] + ("..." if len(text) > 100 else "") + "\n")

            return TTSResult(
                success=True,
                audio_path=output_path,
                subtitle_path=subtitle_path,
                duration_seconds=duration,
            )

        except (TaskCancelled, TaskTimedOut):
            raise
        except Exception as e:
            return TTSResult(
                success=False,
                error=str(e),
            )

    async def generate_batch(
        self,
        texts: list[str],
        output_dir: str,
        filename_prefix: str = "audio",
    ) -> list[TTSResult]:
        """批量生成模拟语音。"""
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for i, text in enumerate(texts):
            output_path = os.path.join(output_dir, f"{filename_prefix}_{i + 1:03d}.mp3")
            result = await self.generate(text, output_path)
            results.append(result)

        return results


def create_tts_generator(
    use_mock: bool = False,
    model: Optional[str] = None,
    voice: Optional[str] = None,
):
    """创建 TTS 生成器。

    Args:
        provider: TTS 提供者 (cosyvoice, edge, ...)，默认从配置读取
        use_mock: 是否使用模拟生成器
        model: 自定义模型名称（仅部分提供商支持）
        voice: 自定义音色名称

    Returns:
        TTS 生成器实例
    """
    if use_mock:
        return MockTTSGenerator()

    return CosyVoiceTTSGenerator(model=model, voice=voice)


def get_voice_by_style(style: str) -> str:
    """根据风格获取推荐语音。

    Args:
        style: 风格名称（narrator, storyteller, news, child, etc.）

    Returns:
        语音名称
    """
    style_mapping = {
        "narrator": "zh-CN-YunjianNeural",  # 解说风格
        "storyteller": "zh-CN-XiaoxiaoNeural",  # 讲故事风格
        "news": "zh-CN-YunyangNeural",  # 新闻播报风格
        "child": "zh-CN-XiaoruiNeural",  # 儿童风格
        "gentle": "zh-CN-XiaoyiNeural",  # 温柔风格
        "mature_female": "zh-CN-XiaomoNeural",  # 成熟女声
        "mature_male": "zh-CN-YunxiNeural",  # 成熟男声
    }

    return style_mapping.get(style, "zh-CN-XiaoxiaoNeural")
