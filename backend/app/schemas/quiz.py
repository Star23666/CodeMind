from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class QuizDifficulty(str, Enum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    CHALLENGE = "challenge"


class QuizQuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    SCENARIO = "scenario"


class QuizCognitiveLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"


class QuizSessionStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class QuizOption(BaseModel):
    id: str = Field(..., min_length=1, max_length=12)
    text: str = Field(..., min_length=1, max_length=500)

    @field_validator("id", "text", mode="before")
    @classmethod
    def strip_values(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class QuizCreateRequest(BaseModel):
    knowledge_base_ids: list[int] = Field(..., min_length=1, max_length=5)
    question_count: int = Field(default=10, ge=5, le=20)
    difficulty: QuizDifficulty = QuizDifficulty.INTERMEDIATE
    question_types: list[QuizQuestionType] = Field(default_factory=list, max_length=6)
    random_mix: bool = True
    topic: str | None = Field(default=None, max_length=100)
    show_explanations_and_sources: bool = True

    @field_validator("knowledge_base_ids")
    @classmethod
    def unique_knowledge_bases(cls, values: list[int]) -> list[int]:
        if any(value < 1 for value in values):
            raise ValueError("知识库 ID 必须为正整数")
        if len(set(values)) != len(values):
            raise ValueError("不能重复选择同一个知识库")
        return values

    @field_validator("question_types")
    @classmethod
    def unique_question_types(
        cls,
        values: list[QuizQuestionType],
    ) -> list[QuizQuestionType]:
        if len(set(values)) != len(values):
            raise ValueError("题型不能重复")
        return values

    @field_validator("topic", mode="before")
    @classmethod
    def normalize_topic(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def validate_type_selection(self):
        if not self.random_mix and not self.question_types:
            raise ValueError("指定题型模式下至少选择一种题型")
        if not self.random_mix and len(self.question_types) > self.question_count:
            raise ValueError("指定题型数量不能超过题目数量")
        if self.random_mix and len(self.question_types) == 1:
            raise ValueError("随机混合模式至少选择两种题型")
        return self


class QuizSource(BaseModel):
    source_id: str
    knowledge_base_id: int
    knowledge_base_name: str
    chunk_id: int
    document_id: int
    file_name: str
    chunk_index: int
    page_no: int | None = None
    source_text: str
    jump_url: str


class QuizQuestionRead(BaseModel):
    id: int
    order_no: int
    question_type: QuizQuestionType
    prompt: str
    options: list[QuizOption] = Field(default_factory=list)
    source_count: int = 0


class QuizSessionRead(BaseModel):
    session_id: str
    status: QuizSessionStatus
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    error_message: str | None = None
    knowledge_base_ids: list[int]
    question_count: int
    difficulty: QuizDifficulty
    question_types: list[QuizQuestionType]
    random_mix: bool
    topic: str | None = None
    show_explanations_and_sources: bool
    expires_at: datetime
    questions: list[QuizQuestionRead] = Field(default_factory=list)


QuizAnswerValue = str | bool | list[str]


class QuizAnswerSubmission(BaseModel):
    question_id: int = Field(..., ge=1)
    answer: QuizAnswerValue | None = None


class QuizSubmitRequest(BaseModel):
    answers: list[QuizAnswerSubmission] = Field(default_factory=list, max_length=20)

    @field_validator("answers")
    @classmethod
    def unique_question_answers(
        cls,
        values: list[QuizAnswerSubmission],
    ) -> list[QuizAnswerSubmission]:
        question_ids = [value.question_id for value in values]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("同一道题不能重复提交答案")
        return values


class QuizQuestionResult(BaseModel):
    question_id: int
    order_no: int
    question_type: QuizQuestionType
    prompt: str
    options: list[QuizOption] = Field(default_factory=list)
    submitted_answer: QuizAnswerValue | None = None
    correct_answer: QuizAnswerValue | None = None
    reference_answer: str | None = None
    is_correct: bool | None = None
    explanation: str | None = None
    sources: list[QuizSource] = Field(default_factory=list)


class QuizSubmissionResult(BaseModel):
    session_id: str
    question_count: int
    auto_scored_count: int
    correct_count: int
    manual_review_count: int
    score_percent: float | None = None
    message: str
    results: list[QuizQuestionResult]


class GeneratedQuizQuestion(BaseModel):
    question_type: QuizQuestionType
    cognitive_level: QuizCognitiveLevel
    prompt: str = Field(..., min_length=4, max_length=1000)
    options: list[QuizOption] = Field(default_factory=list, max_length=8)
    correct_answer: QuizAnswerValue | None = None
    accepted_answers: list[str] = Field(default_factory=list, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    reference_answer: str | None = Field(default=None, max_length=3000)
    explanation: str = Field(..., min_length=4, max_length=3000)
    source_ids: list[str] = Field(..., min_length=1, max_length=5)

    @field_validator("prompt", "explanation", "reference_answer", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("options", mode="before")
    @classmethod
    def normalize_optional_options(cls, value):
        return [] if value is None else value

    @field_validator("accepted_answers", "keywords", mode="before")
    @classmethod
    def normalize_optional_string_lists(cls, values):
        return [] if values is None else values

    @field_validator("accepted_answers", "keywords", "source_ids")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values if value.strip()]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_question_contract(self):
        option_ids = [option.id for option in self.options]
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("选项 ID 不能重复")

        if self.question_type == QuizQuestionType.SINGLE_CHOICE:
            if len(self.options) < 2 or not isinstance(self.correct_answer, str):
                raise ValueError("单选题必须包含选项和一个正确选项 ID")
            if self.correct_answer not in option_ids:
                raise ValueError("单选题答案必须引用现有选项")
        elif self.question_type == QuizQuestionType.MULTIPLE_CHOICE:
            if len(self.options) < 3 or not isinstance(self.correct_answer, list):
                raise ValueError("多选题必须包含选项和正确选项 ID 列表")
            if not self.correct_answer or not set(self.correct_answer).issubset(option_ids):
                raise ValueError("多选题答案必须引用现有选项")
        elif self.question_type == QuizQuestionType.TRUE_FALSE:
            if self.options or not isinstance(self.correct_answer, bool):
                raise ValueError("判断题答案必须为布尔值且不能包含选项")
        elif self.question_type == QuizQuestionType.FILL_BLANK:
            if self.options or (not self.accepted_answers and not self.keywords):
                raise ValueError("填空题必须提供标准答案或关键词")
        elif self.question_type in {
            QuizQuestionType.SHORT_ANSWER,
            QuizQuestionType.SCENARIO,
        }:
            if self.options or not self.reference_answer:
                raise ValueError("主观题必须提供参考答案且不能包含选项")
        return self


class GeneratedQuizPayload(BaseModel):
    questions: list[GeneratedQuizQuestion] = Field(..., min_length=1, max_length=20)
