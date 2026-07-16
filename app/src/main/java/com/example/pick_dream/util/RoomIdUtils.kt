package com.example.pick_dream.util

import com.example.pick_dream.model.LectureRoom

object RoomIdUtils {
    private val buildingNumberByName = mapOf(
        "예지관" to "4",
        "덕문관" to "5",
        "집현관" to "7"
    )

    fun canonicalRoomId(room: LectureRoom): String {
        val explicitRoomId = canonicalRoomId(
            buildingName = room.buildingName,
            buildingDetail = room.buildingDetail.ifBlank { room.displayBuildingName },
            roomName = room.roomID
        )
        if (explicitRoomId.hasCanonicalRoomIdFormat()) return explicitRoomId

        val legacyDocumentId = room.documentId.takeIf { it.hasCanonicalRoomIdFormat() }.orEmpty()
        if (legacyDocumentId.isNotBlank()) return legacyDocumentId

        return canonicalRoomId(
            buildingName = room.buildingName,
            buildingDetail = room.buildingDetail.ifBlank { room.displayBuildingName },
            roomName = room.name
        )
    }

    fun canonicalRoomId(
        buildingName: String,
        buildingDetail: String,
        roomName: String
    ): String {
        extractCanonicalRoomId(roomName)?.let { return it }

        val buildingNumber = buildingNumber(buildingName, buildingDetail)
        val roomNumber = roomNumber(roomName)
        if (buildingNumber.isNotBlank() && roomNumber.isNotBlank()) {
            return buildingNumber + roomNumber
        }

        return ""
    }

    fun roomSearchTerms(room: LectureRoom, headerName: String? = null): List<String> {
        val canonicalId = canonicalRoomId(room)
        val roomDigits = room.name.filter { it.isDigit() }
        val numericDocumentId = room.documentId.takeIf { it.isNumericRoomAlias() }.orEmpty()

        return buildList {
            add(numericDocumentId)
            add(canonicalId)
            add("${canonicalId}호")
            add("${canonicalId}강의실")
            add(room.name)
            add(room.roomID)
            add(roomDigits)
            add(room.buildingName)
            add(room.buildingDetail)
            add(room.displayBuildingName)
            add(headerName.orEmpty())
            addAll(room.equipment)
        }.filter { it.isNotBlank() }.distinct()
    }

    fun matchesSearch(room: LectureRoom, rawQuery: String, headerName: String? = null): Boolean {
        val query = rawQuery.toSearchKey()
        if (query.isBlank()) return true

        return if (query.all { it.isDigit() }) {
            matchesNumericSearch(room, query)
        } else {
            roomSearchTerms(room, headerName).any { term ->
                term.toSearchKey().contains(query)
            }
        }
    }

    fun aliasesForReservationQuery(roomId: String): List<String> {
        val canonical = roomId.trim()
        if (canonical.isBlank()) return emptyList()
        return listOf(canonical)
    }

    fun matchesReservationRoomId(room: LectureRoom, roomId: String): Boolean {
        val query = roomId.trim()
        if (query.isBlank()) return false

        val canonicalId = canonicalRoomId(room)
        if (canonicalId == query) return true
        return false
    }

    fun buildingNumber(buildingName: String, buildingDetail: String): String {
        val sources = listOf(buildingDetail, buildingName)
        for (source in sources) {
            Regex("""(\d+)\s*강의동""").find(source)?.let { return it.groupValues[1] }
        }
        return buildingNumberByName[buildingName].orEmpty()
    }

    private fun matchesNumericSearch(room: LectureRoom, query: String): Boolean {
        val canonicalId = canonicalRoomId(room)
        val roomDigits = room.name.filter { it.isDigit() }
        val numericDocumentId = room.documentId.takeIf { it.isNumericRoomAlias() }.orEmpty()
        val buildingNumber = canonicalId.takeIf { it.isNotBlank() }?.firstOrNull()?.toString().orEmpty()

        if (query.length == 1) {
            return buildingNumber == query
        }

        return listOf(canonicalId, roomDigits, numericDocumentId)
            .filter { it.isNotBlank() }
            .any { it.contains(query) }
    }

    private fun extractCanonicalRoomId(text: String): String? {
        Regex("""(?<!\d)(\d)\s*(?:강의동|동|관)\s*[-\s]?\s*(\d{2,3})(?!\d)\s*호?""")
            .find(text)
            ?.let { return it.groupValues[1] + it.groupValues[2] }

        return Regex("""(?<!\d)(\d{4})(?!\d)\s*호?""")
            .find(text)
            ?.groupValues
            ?.get(1)
    }

    private fun roomNumber(roomName: String): String {
        return Regex("""(?<!\d)\d{2,3}(?!\d)""")
            .findAll(roomName)
            .lastOrNull()
            ?.value
            .orEmpty()
    }

    private fun String.hasCanonicalRoomIdFormat(): Boolean {
        return matches(Regex("""[1-9]\d{3}"""))
    }

    fun isCanonicalRoomId(value: String): Boolean = value.trim().hasCanonicalRoomIdFormat()

    private fun String.isNumericRoomAlias(): Boolean {
        return matches(Regex("""\d{3,4}"""))
    }

    private fun String.toSearchKey(): String {
        return lowercase().replace("\\s+".toRegex(), "")
    }
}
