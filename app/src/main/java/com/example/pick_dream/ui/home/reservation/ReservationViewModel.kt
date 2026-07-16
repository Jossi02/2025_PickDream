package com.example.pick_dream.ui.home.reservation

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.repositoryFailure
import kotlinx.coroutines.launch

class ReservationViewModel : ViewModel() {

    private val _listItems = MutableLiveData<List<ReservationListItem>>()
    val listItems: LiveData<List<ReservationListItem>> get() = _listItems

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> get() = _isLoading

    private val _message = MutableLiveData<String>()
    val message: LiveData<String> get() = _message

    fun loadReservations() {
        _isLoading.value = true

        viewModelScope.launch {
            try {
                val studentId = UserRepository.getCurrentStudentId()
                if (studentId.isNullOrBlank()) {
                    _listItems.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 학번으로 예약 목록 조회
                val reservations = when (
                    val result = ReservationRepository.getReservationsByUser(studentId)
                ) {
                    is RepositoryResult.Success -> result.data
                    is RepositoryResult.Error -> {
                        _message.value = result.failure.userMessage
                        return@launch
                    }
                }
                if (reservations.isEmpty()) {
                    _listItems.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 룸 이미지 조회
                val roomIds = reservations.map { it.roomID }
                val roomImageUrls = when (val result = ReservationRepository.getRoomImages(roomIds)) {
                    is RepositoryResult.Success -> result.data
                    is RepositoryResult.Error -> {
                        _message.value = result.failure.userMessage
                        emptyMap()
                    }
                }

                // 예약 분류 및 정렬
                val now = java.util.Date()
                val upcoming = mutableListOf<Reservation>()
                val past = mutableListOf<Reservation>()

                reservations.forEach { res ->
                    val endTime = parseFlexibleDate(res.endTime)
                    if (endTime != null && endTime.after(now)) {
                        upcoming.add(res)
                    } else {
                        past.add(res)
                    }
                }

                upcoming.sortBy { parseFlexibleDate(it.startTime)?.time ?: Long.MAX_VALUE }
                past.sortByDescending { parseFlexibleDate(it.startTime)?.time ?: 0L }

                val items = mutableListOf<ReservationListItem>()
                if (upcoming.isNotEmpty()) {
                    items.add(ReservationListItem.Header("현재 예약 및 예정된 예약"))
                    items.addAll(upcoming.map { ReservationListItem.ReservationItem(it, roomImageUrls[it.roomID]) })
                }
                if (past.isNotEmpty()) {
                    items.add(ReservationListItem.Header("지난 예약"))
                    items.addAll(past.map { ReservationListItem.ReservationItem(it, roomImageUrls[it.roomID]) })
                }

                _listItems.value = items
            } catch (e: Exception) {
                Log.e("ReservationViewModel", "Failed to load reservations", e)
                _message.value = repositoryFailure("예약 목록 조회", e).userMessage
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun cancelReservation(reservation: Reservation) {
        val docId = reservation.documentId
        if (docId.isBlank()) {
            _message.value = "예약 ID가 없어 취소할 수 없습니다."
            return
        }

        viewModelScope.launch {
            _isLoading.value = true
            when (val result = ReservationRepository.cancelReservation(docId)) {
                is RepositoryResult.Success -> {
                    _message.value = "예약이 취소되었습니다."
                    loadReservations()
                }
                is RepositoryResult.Error -> {
                    _message.value = result.failure.userMessage
                    _isLoading.value = false
                }
            }
        }
    }

    private fun parseFlexibleDate(dateString: String?): java.util.Date? {
        if (dateString.isNullOrBlank()) return null

        val normalized = dateString
            .replace("PM", "오후", ignoreCase = true)
            .replace("AM", "오전", ignoreCase = true)

        val formats = listOf(
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분 s초 'UTC+9'", java.util.Locale.KOREAN),
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분 s초", java.util.Locale.KOREAN),
            java.text.SimpleDateFormat("yyyy년 M월 d일 a h시 m분", java.util.Locale.KOREAN)
        )

        for (format in formats) {
            try { return format.parse(normalized) } catch (e: Exception) { }
        }
        return null
    }
}
