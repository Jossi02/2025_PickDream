package com.example.pick_dream.ui.home.reservation

import com.example.pick_dream.model.LectureRoom
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.util.RoomIdUtils
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.firestore.ktx.toObject
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await

object ReservationRepository {
    private val db = Firebase.firestore

    /**
     * 특정 유저(학번)의 예약 목록을 최신순으로 가져옵니다.
     */
    suspend fun getReservationsByUser(studentId: String): List<Reservation> {
        return try {
            val snapshot = db.collection("Reservations")
                .whereEqualTo("userID", studentId)
                // 인덱스 오류 방지를 위해 orderBy 제거 후 앱 단에서 정렬
                .get()
                .await()

            snapshot.documents.mapNotNull { doc ->
                doc.toObject<Reservation>()?.apply { documentId = doc.id }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 특정 방의 예약 목록을 가져옵니다.
     */
    suspend fun getReservationsByRoom(roomId: String): List<Reservation> {
        return try {
            val roomIds = RoomIdUtils.aliasesForReservationQuery(roomId)

            val reservationsByDocumentId = linkedMapOf<String, Reservation>()
            roomIds.forEach { id ->
                val snapshot = db.collection("Reservations")
                    .whereEqualTo("roomID", id)
                    .get()
                    .await()

                snapshot.documents.forEach { doc ->
                    doc.toObject<Reservation>()?.apply { documentId = doc.id }?.let { reservation ->
                        reservationsByDocumentId[doc.id] = reservation
                    }
                }
            }

            reservationsByDocumentId.values.toList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    /**
     * 예약 목록의 방 ID들을 기반으로 방 이미지를 가져옵니다.
     */
    suspend fun getRoomImages(roomIds: List<String>): Map<String, String?> {
        val uniqueIds = roomIds.distinct().filter { it.isNotBlank() }
        if (uniqueIds.isEmpty()) return emptyMap()

        val map = mutableMapOf<String, String?>()
        try {
            val roomDocuments = db.collection("rooms").get().await().documents
            val roomDocumentPairs = roomDocuments.mapNotNull { doc ->
                doc.toObject<LectureRoom>()?.copy(id = doc.id)?.let { room ->
                    room to doc
                }
            }

            uniqueIds.forEach { roomId ->
                val doc = roomDocumentPairs.firstOrNull { (room, _) ->
                    RoomIdUtils.matchesReservationRoomId(room, roomId)
                }?.second
                map[roomId] = doc?.getString("image") ?: doc?.getString("imageUrl")
            }
        } catch (e: Exception) {
            // 실패 시 빈 맵 반환 (기본 이미지 처리를 위해)
        }
        return map
    }

    /**
     * 새로운 예약을 추가합니다.
     */
    suspend fun addReservation(reservation: Reservation): Boolean {
        return try {
            val ownerUid = FirebaseAuth.getInstance().currentUser?.uid ?: return false
            val normalizedRoomId = RoomIdUtils.aliasesForReservationQuery(reservation.roomID)
                .firstOrNull()
                ?: reservation.roomID.trim()
            db.collection("Reservations")
                .add(reservation.copy(ownerUid = ownerUid, roomID = normalizedRoomId))
                .await()
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * 특정 예약을 취소(삭제)합니다.
     */
    suspend fun cancelReservation(documentId: String): Boolean {
        return try {
            db.collection("Reservations").document(documentId).delete().await()
            true
        } catch (e: Exception) {
            false
        }
    }
}
