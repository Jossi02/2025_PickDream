package com.example.pick_dream.ui.home.search

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MediatorLiveData
import androidx.lifecycle.MutableLiveData
import com.example.pick_dream.model.LectureRoom
import com.example.pick_dream.repository.NetworkStatus
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.authenticationFailure
import com.example.pick_dream.repository.awaitWithTimeout
import com.example.pick_dream.repository.networkFailure
import com.example.pick_dream.repository.repositoryFailure
import com.example.pick_dream.util.RoomIdUtils
import com.google.firebase.firestore.ktx.toObject
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.TransactionOptions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

sealed class ListItem {
    data class HeaderItem(val buildingName: String) : ListItem()
    data class RoomItem(val lectureRoom: LectureRoom) : ListItem()
}

object LectureRoomRepository {
    private val db = FirebaseFirestore.getInstance()
    private val allRooms = MutableLiveData<List<LectureRoom>>()
    private val favoriteRoomIds = MutableLiveData<List<String>>()
    private val repositoryScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private fun normalizeRoom(rawRoom: LectureRoom, documentId: String): LectureRoom {
        val roomWithDocumentId = rawRoom.copy(documentId = documentId)
        return roomWithDocumentId.copy(
            roomID = RoomIdUtils.canonicalRoomId(roomWithDocumentId)
        )
    }

    // 최종적으로 UI에 보여줄 LiveData. allRooms나 favoriteRoomIds가 변경되면 자동으로 업데이트됨
    val lectureRoomsWithFavorites = MediatorLiveData<List<ListItem>>()

    init {
        // 두 LiveData를 관찰하고, 변경이 있을 때마다 데이터를 조합하는 로직
        lectureRoomsWithFavorites.addSource(allRooms) { rooms ->
            combineRoomsAndFavorites(rooms, favoriteRoomIds.value)
        }
        lectureRoomsWithFavorites.addSource(favoriteRoomIds) { ids ->
            combineRoomsAndFavorites(allRooms.value, ids)
        }
    }

    private fun combineRoomsAndFavorites(rooms: List<LectureRoom>?, ids: List<String>?) {
        if (rooms == null || ids == null) {
            return
        }

        val updatedRooms = rooms.map { room ->
            room.copy(isFavorite = ids.contains(room.documentId))
        }

        // displayBuildingName에서 숫자(강의동 번호)를 추출하여 건물별로 먼저 정렬하고, 그 다음 강의실 번호로 정렬
        val sortedRooms = updatedRooms.sortedWith(
            compareBy<LectureRoom> { room ->
                // "덕문관 (5강의동)" -> 5
                room.displayBuildingName.filter { it.isDigit() }.toIntOrNull() ?: 999
            }.thenBy {
                // "5104" -> 5104
                it.name.filter { char -> char.isDigit() }.toIntOrNull() ?: 0
            }
        )

        val groupedList = mutableListOf<ListItem>()
        var lastBuildingName = ""
        sortedRooms.forEach { room ->
            if (room.buildingName != lastBuildingName) {
                val headerText = room.displayBuildingName
                groupedList.add(ListItem.HeaderItem(headerText))
                lastBuildingName = room.buildingName
            }
            groupedList.add(ListItem.RoomItem(room))
        }
        
        lectureRoomsWithFavorites.postValue(groupedList)
    }

    fun fetchRooms() {
        if (allRooms.value != null && allRooms.value!!.isNotEmpty()) {
            Log.d("LectureRoomRepo", "Rooms already fetched. Skipping.")
            return
        }
        
        Log.d("LectureRoomRepo", "Fetching rooms from Firestore.")
        repositoryScope.launch {
            try {
                val result = db.collection("rooms").get().awaitWithTimeout()
                val roomList = result.mapNotNull { doc ->
                    normalizeRoom(doc.toObject<LectureRoom>(), doc.id)
                }
                allRooms.postValue(roomList)
                Log.d("LectureRoomRepo", "Successfully fetched ${roomList.size} rooms.")
            } catch (e: Exception) {
                Log.e("LectureRoomRepo", "Error fetching rooms", e)
            }
        }
    }

    fun fetchFavoriteIds() {
        val uid = UserRepository.getCurrentUid() ?: run {
            favoriteRoomIds.postValue(emptyList()) // 로그인하지 않은 사용자는 빈 찜 목록
            return
        }
        // 실시간 업데이트를 위해 addSnapshotListener 사용
        db.collection("User").document(uid)
            .addSnapshotListener { snapshot, e ->
                if (e != null) {
                    Log.w("LectureRoomRepo", "Listen failed.", e)
                    return@addSnapshotListener
                }

                if (snapshot != null && snapshot.exists()) {
                    if (snapshot.metadata.hasPendingWrites()) {
                        Log.d("LectureRoomRepo", "Ignoring pending favorite changes.")
                        return@addSnapshotListener
                    }
                    // 이제 찜 목록 필드 이름은 'favoriteRooms' 입니다.
                    val ids = snapshot.get("favoriteRooms") as? List<String> ?: emptyList()
                    favoriteRoomIds.postValue(ids)
                    Log.d("LectureRoomRepo", "Favorite IDs updated: $ids")
                } else {
                    Log.d("LectureRoomRepo", "Current data: null")
                    favoriteRoomIds.postValue(emptyList())
                }
            }
    }

    fun toggleFavorite(
        roomId: String,
        onResult: (RepositoryResult<Boolean>) -> Unit
    ) {
        val uid = UserRepository.getCurrentUid() ?: run {
            onResult(RepositoryResult.Error(authenticationFailure("찜 변경")))
            return
        }
        if (!NetworkStatus.hasValidatedInternet()) {
            onResult(RepositoryResult.Error(networkFailure("찜 변경")))
            return
        }
        val userDocRef = db.collection("User").document(uid)

        val transactionOptions = TransactionOptions.Builder()
            .setMaxAttempts(1)
            .build()
        repositoryScope.launch {
            try {
                val isNowFavorite = db.runTransaction(transactionOptions) { transaction ->
                    val snapshot = transaction.get(userDocRef)
                    val favoriteIds = (snapshot.get("favoriteRooms") as? List<*>)
                        .orEmpty()
                        .filterIsInstance<String>()
                        .toMutableSet()
                    val newState = if (favoriteIds.remove(roomId)) {
                        false
                    } else {
                        favoriteIds.add(roomId)
                        true
                    }
                    transaction.update(userDocRef, "favoriteRooms", favoriteIds.toList())
                    newState
                }.awaitWithTimeout()
                Log.d("LectureRoomRepo", "Favorite state confirmed for $roomId: $isNowFavorite")
                onResult(RepositoryResult.Success(isNowFavorite))
            } catch (error: Exception) {
                onResult(RepositoryResult.Error(repositoryFailure("찜 변경", error)))
            }
        }
    }

    /**
     * 이름으로 강의실 단건을 조회합니다. ViewModel에서 캐시 미스 발생 시 사용합니다.
     * @param roomName 조회할 강의실 이름
     * @param onResult 조회 결과 콜백
     */
    fun fetchRoomByName(roomName: String, onResult: (LectureRoom?) -> Unit) {
        repositoryScope.launch {
            try {
                val documents = db.collection("rooms")
                    .whereEqualTo("name", roomName)
                    .get()
                    .awaitWithTimeout()
                val room = documents.firstOrNull()?.let { doc ->
                    normalizeRoom(doc.toObject<LectureRoom>(), doc.id)
                }
                onResult(room)
            } catch (error: Exception) {
                Log.e("LectureRoomRepo", "Error fetching room by name: $roomName", error)
                onResult(null)
            }
        }
    }

    fun fetchRoomByCanonicalId(roomId: String, onResult: (LectureRoom?) -> Unit) {
        val canonicalRoomId = RoomIdUtils.aliasesForReservationQuery(roomId).firstOrNull() ?: roomId.trim()
        val cachedRoom = allRooms.value?.firstOrNull { room ->
            RoomIdUtils.matchesReservationRoomId(room, canonicalRoomId)
        }
        if (cachedRoom != null) {
            onResult(cachedRoom)
            return
        }

        repositoryScope.launch {
            try {
                val documents = db.collection("rooms").get().awaitWithTimeout()
                val room = documents.mapNotNull { doc ->
                    normalizeRoom(doc.toObject<LectureRoom>(), doc.id)
                }.firstOrNull { room ->
                    RoomIdUtils.matchesReservationRoomId(room, canonicalRoomId)
                }
                onResult(room)
            } catch (error: Exception) {
                Log.e("LectureRoomRepo", "Error fetching room by canonical id: $canonicalRoomId", error)
                onResult(null)
            }
        }
    }
}
