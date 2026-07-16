package com.example.pick_dream

import com.example.pick_dream.model.LectureRoom
import com.example.pick_dream.util.RoomIdUtils
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RoomIdUtilsTest {
    @Test
    fun canonicalRoomId_buildsIdFromBuildingAndRoomName() {
        val room = LectureRoom(
            documentId = "room-7202",
            roomID = "7202",
            name = "집현관 202호",
            buildingName = "집현관",
            buildingDetail = "7강의동"
        )

        assertEquals("7202", RoomIdUtils.canonicalRoomId(room))
    }

    @Test
    fun numericSearch_singleDigitMatchesOnlyBuildingNumber() {
        val roomInSeven = LectureRoom(
            documentId = "room-7202",
            roomID = "7202",
            name = "집현관 202호",
            buildingName = "집현관",
            buildingDetail = "7강의동"
        )
        val roomInFive = LectureRoom(
            documentId = "room-5101",
            roomID = "5101",
            name = "덕문관 101호",
            buildingName = "덕문관",
            buildingDetail = "5강의동"
        )

        assertTrue(RoomIdUtils.matchesSearch(roomInSeven, "7"))
        assertFalse(RoomIdUtils.matchesSearch(roomInFive, "7"))
    }

    @Test
    fun numericSearch_fullRoomIdMatchesCanonicalId() {
        val room = LectureRoom(
            documentId = "room-7202",
            roomID = "7202",
            name = "집현관 202호",
            buildingName = "집현관",
            buildingDetail = "7강의동"
        )

        assertTrue(RoomIdUtils.matchesSearch(room, "7202"))
        assertTrue(RoomIdUtils.matchesSearch(room, "202"))
    }

    @Test
    fun reservationAliasesIncludeLegacyRoomNumber() {
        assertEquals(listOf("7202"), RoomIdUtils.aliasesForReservationQuery("7202"))
        assertFalse(
            RoomIdUtils.matchesReservationRoomId(
                LectureRoom(roomID = "7202", name = "집현관 202호"),
                "202"
            )
        )
    }

    @Test
    fun explicitRoomIdWinsOverOpaqueDocumentIdAndDisplayText() {
        val room = LectureRoom(
            documentId = "opaque-document-key",
            roomID = "7202",
            name = "다른 표시 이름",
            buildingName = "집현관",
            buildingDetail = "7강의동"
        )

        assertEquals("7202", RoomIdUtils.canonicalRoomId(room))
    }

    @Test
    fun legacyRoomNumberRequiresBuildingContextToBecomeCanonical() {
        assertEquals(
            "7202",
            RoomIdUtils.canonicalRoomId("집현관", "7강의동", "202호")
        )
        assertEquals("", RoomIdUtils.canonicalRoomId("", "", "202"))
    }
}
