"""tests/test_llm.py — Unit tests for the LLM factory (core/llm.py)."""

from __future__ import annotations

import builtins
import sys
from unittest.mock import MagicMock, patch

import pytest

from core.llm import LLMConfig, get_llm


class TestGetLlmAnthropic:
    def test_returns_chat_anthropic(self):
        mock_model = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "langchain_anthropic": MagicMock(
                    ChatAnthropic=MagicMock(return_value=mock_model)
                )
            },
        ):
            config = LLMConfig(provider="anthropic", anthropic_api_key="sk-ant-test123")
            result = get_llm(config)
        assert result is mock_model

    def test_raises_without_api_key(self):
        with patch.dict(
            "sys.modules",
            {"langchain_anthropic": MagicMock(ChatAnthropic=MagicMock())},
        ):
            config = LLMConfig(provider="anthropic", anthropic_api_key=None)
            with pytest.raises(ValueError, match="anthropic_api_key"):
                get_llm(config)

    def test_raises_on_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``langchain_anthropic`` cannot be loaded, get_llm must raise ImportError."""
        real_import = builtins.__import__

        def _guard_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ):
            if level == 0 and name == "langchain_anthropic":
                raise ImportError("simulated missing langchain_anthropic")
            return real_import(name, globals_arg, locals_arg, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _guard_import)
        monkeypatch.delitem(sys.modules, "langchain_anthropic", raising=False)
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-ant-test123")
        with pytest.raises(ImportError):
            get_llm(config)


class TestGetLlmOpenAI:
    def test_returns_chat_openai(self):
        mock_model = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "langchain_openai": MagicMock(
                    ChatOpenAI=MagicMock(return_value=mock_model)
                )
            },
        ):
            config = LLMConfig(provider="openai", openai_api_key="sk-openai-test")
            result = get_llm(config)
        assert result is mock_model

    def test_raises_without_api_key(self):
        with patch.dict(
            "sys.modules",
            {"langchain_openai": MagicMock(ChatOpenAI=MagicMock())},
        ):
            config = LLMConfig(provider="openai", openai_api_key=None)
            with pytest.raises(ValueError, match="openai_api_key"):
                get_llm(config)


class TestGetLlmOllama:
    def test_returns_chat_ollama(self):
        mock_model = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "langchain_ollama": MagicMock(
                    ChatOllama=MagicMock(return_value=mock_model)
                )
            },
        ):
            config = LLMConfig(provider="ollama")
            result = get_llm(config)
        assert result is mock_model


class TestGetLlmUnknown:
    def test_raises_on_unknown_provider(self):
        # Force an unknown provider via direct config construction
        config = LLMConfig.__new__(LLMConfig)
        object.__setattr__(config, "provider", "unknown_provider")
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm(config)


class TestGetLlmGoogle:
    def test_returns_chat_google(self) -> None:
        mock_model = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatGoogleGenerativeAI.return_value = mock_model
        with patch.dict("sys.modules", {"langchain_google_genai": mock_module}):
            config = LLMConfig(provider="google", google_api_key="gai-test-key")
            result = get_llm(config)
        assert result is mock_model

    def test_raises_without_api_key(self) -> None:
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_google_genai": mock_module}):
            config = LLMConfig(provider="google", google_api_key=None)
            with pytest.raises(ValueError, match="google_api_key"):
                get_llm(config)


class TestGetLlmBedrock:
    def test_returns_chat_bedrock(self) -> None:
        mock_model = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatBedrock.return_value = mock_model
        with patch.dict("sys.modules", {"langchain_aws": mock_module}):
            config = LLMConfig(
                provider="bedrock",
                aws_access_key_id="AKIATEST",
                aws_secret_access_key="secret",
            )
            result = get_llm(config)
        assert result is mock_model

    def test_raises_without_access_key(self) -> None:
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": mock_module}):
            config = LLMConfig(provider="bedrock", aws_access_key_id=None)
            with pytest.raises(ValueError, match="aws_access_key_id"):
                get_llm(config)

    def test_raises_without_secret_key(self) -> None:
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": mock_module}):
            config = LLMConfig(
                provider="bedrock",
                aws_access_key_id="AKIATEST",
                aws_secret_access_key=None,
            )
            with pytest.raises(ValueError, match="aws_secret_access_key"):
                get_llm(config)


class TestGetLlmAzure:
    def test_returns_azure_chat_openai(self) -> None:
        mock_model = MagicMock()
        mock_module = MagicMock()
        mock_module.AzureChatOpenAI.return_value = mock_model
        with patch.dict("sys.modules", {"langchain_openai": mock_module}):
            config = LLMConfig(
                provider="azure",
                azure_openai_api_key="azure-key",
                azure_openai_endpoint="https://my-resource.openai.azure.com/",
            )
            result = get_llm(config)
        assert result is mock_model

    def test_raises_without_api_key(self) -> None:
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": mock_module}):
            config = LLMConfig(provider="azure", azure_openai_api_key=None)
            with pytest.raises(ValueError, match="azure_openai_api_key"):
                get_llm(config)

    def test_raises_without_endpoint(self) -> None:
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": mock_module}):
            config = LLMConfig(
                provider="azure",
                azure_openai_api_key="azure-key",
                azure_openai_endpoint=None,
            )
            with pytest.raises(ValueError, match="azure_openai_endpoint"):
                get_llm(config)


# ---------------------------------------------------------------------------
# ImportError handling for each provider
# ---------------------------------------------------------------------------


class TestGetLlmImportErrors:
    """get_llm should raise ImportError when the provider package is missing."""

    def test_openai_import_error(self) -> None:
        """get_llm should raise ImportError when langchain_openai is missing."""
        config = LLMConfig(provider="openai", openai_api_key="sk-test1234567890")
        with patch.dict("sys.modules", {"langchain_openai": None}):
            with pytest.raises(ImportError):
                get_llm(config)

    def test_google_import_error(self) -> None:
        """get_llm should raise ImportError when langchain_google_genai is missing."""
        config = LLMConfig(provider="google", google_api_key="test-key-abcdef")
        with patch.dict("sys.modules", {"langchain_google_genai": None}):
            with pytest.raises(ImportError):
                get_llm(config)

    def test_azure_import_error(self) -> None:
        """get_llm should raise ImportError when langchain_openai is missing (Azure)."""
        config = LLMConfig(
            provider="azure",
            azure_openai_api_key="azure-key",
            azure_openai_endpoint="https://my-resource.openai.azure.com/",
        )
        with patch.dict("sys.modules", {"langchain_openai": None}):
            with pytest.raises(ImportError):
                get_llm(config)

    def test_ollama_import_error(self) -> None:
        """get_llm should raise ImportError when langchain_ollama is missing."""
        config = LLMConfig(provider="ollama")
        with patch.dict("sys.modules", {"langchain_ollama": None}):
            with pytest.raises(ImportError):
                get_llm(config)


# ---------------------------------------------------------------------------
# LLMConfig defaults
# ---------------------------------------------------------------------------


class TestGetLlmMock:
    """Mock provider should work without any API key."""

    def test_returns_fake_model(self):
        config = LLMConfig(provider="mock")
        llm = get_llm(config)
        assert llm is not None

    def test_mock_returns_string_response(self):
        config = LLMConfig(provider="mock")
        llm = get_llm(config)
        from langchain_core.messages import HumanMessage

        result = llm.invoke([HumanMessage(content="test")])
        assert isinstance(result.content, str)
        assert len(result.content) > 0


class TestLLMConfigDefaults:
    """Verify LLMConfig provides sensible defaults."""

    def test_default_anthropic_model(self) -> None:
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-ant-test123")
        assert "claude" in config.anthropic_model.lower()

    def test_default_max_tokens(self) -> None:
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-ant-test123")
        assert config.max_tokens > 0

    def test_default_request_timeout(self) -> None:
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-ant-test123")
        assert config.request_timeout_seconds == 120.0


class TestGetLlmTimeoutPropagation:
    def test_anthropic_receives_default_request_timeout(self) -> None:
        mock_ctor = MagicMock(return_value=MagicMock())
        with patch.dict(
            "sys.modules",
            {"langchain_anthropic": MagicMock(ChatAnthropic=mock_ctor)},
        ):
            config = LLMConfig(
                provider="anthropic",
                anthropic_api_key="sk-ant-test123",
                request_timeout_seconds=90.0,
            )
            get_llm(config)
        mock_ctor.assert_called_once()
        assert mock_ctor.call_args.kwargs["default_request_timeout"] == 90.0

    def test_openai_receives_request_timeout(self) -> None:
        mock_ctor = MagicMock(return_value=MagicMock())
        with patch.dict(
            "sys.modules",
            {"langchain_openai": MagicMock(ChatOpenAI=mock_ctor)},
        ):
            config = LLMConfig(
                provider="openai",
                openai_api_key="sk-openai-test",
                request_timeout_seconds=75.0,
            )
            get_llm(config)
        assert mock_ctor.call_args.kwargs["request_timeout"] == 75.0
