package com.example.pick_dream.ui.home.search

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.example.pick_dream.model.LectureRoom

/**
 * LectureRoomDetailFragment의 UI 상태를 관리하는 ViewModel.
 * Firestore 접근은 LectureRoomRepository에 위임합니다.
 */
class LectureRoomDetailViewModel : ViewModel() {

    private val _roomDetail = MutableLiveData<LectureRoom?>()
    val roomDetail: LiveData<LectureRoom?> = _roomDetail

    /**
     * 강의실 이름(roomName)으로 강의실 상세 정보를 불러옵니다.
     * 이미 캐시된 데이터(allRooms)에서 찾아 Firestore 추가 호출을 방지합니다.
     */
    fun loadRoomDetail(roomId: String, roomName: String) {
        // LectureRoomRepository의 캐시 데이터에서 먼저 탐색
        val cachedRoom = LectureRoomRepository.lectureRoomsWithFavorites.value
            ?.filterIsInstance<ListItem.RoomItem>()
            ?.find {
                it.lectureRoom.roomID == roomId ||
                    (roomId.isBlank() && it.lectureRoom.name == roomName)
            }
            ?.lectureRoom

        if (cachedRoom != null) {
            _roomDetail.value = cachedRoom
        } else {
            // 캐시에 없는 경우 Repository를 통해 재조회
            val loader = if (roomId.isNotBlank()) {
                { callback: (LectureRoom?) -> Unit ->
                    LectureRoomRepository.fetchRoomByCanonicalId(roomId, callback)
                }
            } else {
                { callback: (LectureRoom?) -> Unit ->
                    LectureRoomRepository.fetchRoomByName(roomName, callback)
                }
            }
            loader { room ->
                _roomDetail.postValue(room)
            }
        }
    }
}
