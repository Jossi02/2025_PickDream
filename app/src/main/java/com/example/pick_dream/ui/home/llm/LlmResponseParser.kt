package com.example.pick_dream.ui.home.llm

import org.json.JSONObject

object LlmResponseParser {
    private const val SUPPORTED_SCHEMA_VERSION = 1
    private const val RESPONSE_KIND = "assistant_response"

    fun parse(raw: String): LlmMessage {
        return runCatching {
            val json = JSONObject(raw)
            val schemaVersion = json.optInt("schemaVersion", 0)
            val kind = json.optString("kind")
            val isLegacyEnvelope = schemaVersion == 0 && kind.isBlank()
            val isSupportedEnvelope =
                schemaVersion in 1..SUPPORTED_SCHEMA_VERSION && kind == RESPONSE_KIND

            if (!isLegacyEnvelope && !isSupportedEnvelope) {
                return@runCatching LlmMessage(raw, false)
            }

            val text = json.optString("text", raw)
            val title = json.optString("title").takeIf { it.isNotBlank() }
            val cardsJson = json.optJSONArray("cards")
            val cards = buildList {
                if (cardsJson == null) return@buildList
                for (i in 0 until cardsJson.length()) {
                    val cardJson = cardsJson.optJSONObject(i) ?: continue
                    val roomName = cardJson.optString("roomName")
                    if (roomName.isBlank()) continue

                    val actionsJson = cardJson.optJSONArray("actions")
                    val actions = buildList {
                        if (actionsJson == null) return@buildList
                        for (j in 0 until actionsJson.length()) {
                            val actionJson = actionsJson.optJSONObject(j) ?: continue
                            val label = actionJson.optString("label")
                            val message = actionJson.optString("message")
                            if (label.isBlank() || message.isBlank()) continue
                            add(
                                LlmAction(
                                    label = label,
                                    message = message,
                                    displayText = actionJson.optString("displayText", label)
                                )
                            )
                        }
                    }

                    add(
                        LlmCard(
                            type = cardJson.optString("type"),
                            roomName = roomName,
                            description = cardJson.optString("description"),
                            startTime = cardJson.optString("startTime"),
                            endTime = cardJson.optString("endTime"),
                            participants = cardJson.optString("participants")
                                .takeIf { it.isNotBlank() },
                            actions = actions
                        )
                    )
                }
            }

            LlmMessage(text = text, isUser = false, title = title, cards = cards)
        }.getOrElse {
            LlmMessage(raw, false)
        }
    }
}
