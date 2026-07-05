package com.example.pick_dream.ui.home

import android.content.Context
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.UserRepository
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.ktx.toObject

/**
 * HomeFragment에서 필요한 데이터 접근 로직(Firestore, SharedPreferences)을 담당하는 Repository 클래스.
 * Fragment에서 직접 DB를 다루지 않고 이 클래스를 통해서만 데이터에 접근합니다.
 */
object HomeRepository {

    private val db = FirebaseFirestore.getInstance()

    /**
     * 현재 로그인한 사용자의 예약 목록 중 진행 중이거나 가장 가까운 예정 예약을 콜백으로 반환합니다.
     * @param onResult 조회 결과 콜백. 유효한 예약이 없으면 null을 반환합니다.
     */
    fun fetchActiveOrUpcomingReservation(onResult: (Reservation?) -> Unit) {
        UserRepository.getCurrentStudentId { studentId ->
                if (studentId.isNullOrBlank()) {
                    onResult(null)
                    return@getCurrentStudentId
                }

                db.collection("Reservations")
                    .whereEqualTo("userID", studentId)
                    .get()
                    .addOnSuccessListener { snapshot ->
                        val now = java.util.Calendar.getInstance()
                        val reservations = snapshot.documents.mapNotNull { it.toObject<Reservation>() }

                        val active = reservations.firstOrNull {
                            val start = it.startTime?.let { s -> parseKoreanDateToCalendar(s) }
                            val end = it.endTime?.let { e -> parseKoreanDateToCalendar(e) }
                            start != null && end != null && !now.before(start) && now.before(end)
                        }

                        val upcoming = if (active == null) {
                            reservations.filter {
                                val start = it.startTime?.let { s -> parseKoreanDateToCalendar(s) }
                                start != null && now.before(start)
                            }.minByOrNull { parseKoreanDateToCalendar(it.startTime!!)!!.timeInMillis }
                        } else null

                        onResult(active ?: upcoming)
                    }
                    .addOnFailureListener { onResult(null) }
        }
    }

    /**
     * 현재 예약 정보를 SharedPreferences에 저장합니다. (앱 재시작 시 리뷰 팝업 표시에 사용)
     */
    fun saveReservationPrefs(context: Context, endTimeMillis: Long, roomId: String) {
        val prefs = context.getSharedPreferences("ClassroomPrefs", Context.MODE_PRIVATE)
        val savedEndTime = prefs.getLong("last_end_time", 0)
        val savedRoomId = prefs.getString("last_room_id", null)

        if (savedEndTime != endTimeMillis || savedRoomId != roomId) {
            prefs.edit().apply {
                putLong("last_end_time", endTimeMillis)
                putString("last_room_id", roomId)
                putBoolean("has_shown_review", false)
                apply()
            }
        }
    }
}
