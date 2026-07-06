package com.example.pick_dream.ui.home.llm

data class LlmMessage(
    val text: String,
    val isUser: Boolean,
    val title: String? = null,
    val cards: List<LlmCard> = emptyList()
)

data class LlmCard(
    val type: String,
    val roomName: String,
    val description: String = "",
    val startTime: String = "",
    val endTime: String = "",
    val participants: String? = null,
    val actions: List<LlmAction> = emptyList()
)

data class LlmAction(
    val label: String,
    val message: String,
    val displayText: String = label
)
