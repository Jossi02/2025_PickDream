package com.example.pick_dream.ui.home.reservation

import com.example.pick_dream.model.LectureRoom
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.NetworkStatus
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.authenticationFailure
import com.example.pick_dream.repository.awaitWithTimeout
import com.example.pick_dream.repository.dataFailure
import com.example.pick_dream.repository.networkFailure
import com.example.pick_dream.repository.repositoryFailure
import com.example.pick_dream.util.RoomIdUtils
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.firestore.ktx.toObject
import com.google.firebase.firestore.TransactionOptions
import com.google.firebase.ktx.Firebase

object ReservationRepository {
    private val db = Firebase.firestore
    private val transactionOptions = TransactionOptions.Builder()
        .setMaxAttempts(1)
        .build()

    /**
     * 특정 유저(학번)의 예약 목록을 최신순으로 가져옵니다.
     */
    suspend fun getReservationsByUser(studentId: String): RepositoryResult<List<Reservation>> {
        return try {
            val snapshot = db.collection("Reservations")
                .whereEqualTo("userID", studentId)
                // 인덱스 오류 방지를 위해 orderBy 제거 후 앱 단에서 정렬
                .get()
                .awaitWithTimeout()

            RepositoryResult.Success(
                snapshot.documents
                    .filterNot { it.metadata.hasPendingWrites() }
                    .mapNotNull { doc ->
                        doc.toObject<Reservation>()?.apply { documentId = doc.id }
                    }
            )
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("예약 목록 조회", e))
        }
    }

    /**
     * 특정 방의 예약 목록을 가져옵니다.
     */
    suspend fun getReservationsByRoom(roomId: String): RepositoryResult<List<Reservation>> {
        return try {
            val roomIds = RoomIdUtils.aliasesForReservationQuery(roomId)

            val reservationsByDocumentId = linkedMapOf<String, Reservation>()
            roomIds.forEach { id ->
                val snapshot = db.collection("Reservations")
                    .whereEqualTo("roomID", id)
                    .get()
                    .awaitWithTimeout()

                snapshot.documents
                    .filterNot { it.metadata.hasPendingWrites() }
                    .forEach { doc ->
                    doc.toObject<Reservation>()?.apply { documentId = doc.id }?.let { reservation ->
                        reservationsByDocumentId[doc.id] = reservation
                    }
                }
            }

            RepositoryResult.Success(reservationsByDocumentId.values.toList())
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("강의실 예약 조회", e))
        }
    }

    /**
     * 예약 목록의 방 ID들을 기반으로 방 이미지를 가져옵니다.
     */
    suspend fun getRoomImages(roomIds: List<String>): RepositoryResult<Map<String, String?>> {
        val uniqueIds = roomIds.distinct().filter { it.isNotBlank() }
        if (uniqueIds.isEmpty()) return RepositoryResult.Success(emptyMap())

        val map = mutableMapOf<String, String?>()
        return try {
            val roomDocuments = db.collection("rooms").get().awaitWithTimeout().documents
            val roomDocumentPairs = roomDocuments.mapNotNull { doc ->
                doc.toObject<LectureRoom>()?.let { rawRoom ->
                    val roomWithDocumentId = rawRoom.copy(documentId = doc.id)
                    roomWithDocumentId.copy(
                        roomID = RoomIdUtils.canonicalRoomId(roomWithDocumentId)
                    ) to doc
                }
            }

            uniqueIds.forEach { roomId ->
                val doc = roomDocumentPairs.firstOrNull { (room, _) ->
                    RoomIdUtils.matchesReservationRoomId(room, roomId)
                }?.second
                map[roomId] = doc?.getString("image") ?: doc?.getString("imageUrl")
            }
            RepositoryResult.Success(map)
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("강의실 이미지 조회", e))
        }
    }

    /**
     * 새로운 예약을 추가합니다.
     */
    suspend fun addReservation(reservation: Reservation): RepositoryResult<Unit> {
        return try {
            val ownerUid = UserRepository.getCurrentUid()
                ?: return RepositoryResult.Error(authenticationFailure("예약 생성"))
            if (!NetworkStatus.hasValidatedInternet()) {
                return RepositoryResult.Error(networkFailure("예약 생성"))
            }
            val normalizedRoomId = reservation.roomID.trim()
            if (!RoomIdUtils.isCanonicalRoomId(normalizedRoomId)) {
                return RepositoryResult.Error(dataFailure("예약 생성"))
            }
            val document = db.collection("Reservations").document()
            val normalizedReservation = reservation.copy(
                ownerUid = ownerUid,
                roomID = normalizedRoomId
            )
            db.runTransaction(transactionOptions) { transaction ->
                transaction.set(document, normalizedReservation)
                Unit
            }.awaitWithTimeout()
            RepositoryResult.Success(Unit)
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("예약 생성", e))
        }
    }

    /**
     * 특정 예약을 취소(삭제)합니다.
     */
    suspend fun cancelReservation(documentId: String): RepositoryResult<Unit> {
        return try {
            if (!NetworkStatus.hasValidatedInternet()) {
                return RepositoryResult.Error(networkFailure("예약 취소"))
            }
            val document = db.collection("Reservations").document(documentId)
            db.runTransaction(transactionOptions) { transaction ->
                transaction.delete(document)
                Unit
            }.awaitWithTimeout()
            RepositoryResult.Success(Unit)
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("예약 취소", e))
        }
    }
}
