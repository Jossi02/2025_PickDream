package com.example.pick_dream.ui.home.search.manualReservation

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.ui.home.reservation.ReservationRepository
import com.example.pick_dream.util.ReservationTimeUtils
import com.prolificinteractive.materialcalendarview.CalendarDay
import kotlinx.coroutines.launch

class ManualReservationViewModel : ViewModel() {
    var selectedDay: CalendarDay? = null
    var startHour: Int? = null
    var startMinute: Int? = null
    var endHour: Int? = null
    var endMinute: Int? = null
    var selectedEquipments: List<String> = emptyList()

    private val _isSubmitting = MutableLiveData<Boolean>()
    val isSubmitting: LiveData<Boolean> get() = _isSubmitting

    private val _submitResult = MutableLiveData<Boolean?>()
    val submitResult: LiveData<Boolean?> get() = _submitResult
    
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> get() = _errorMessage

    private val _existingReservations = MutableLiveData<List<Reservation>>()
    val existingReservations: LiveData<List<Reservation>> get() = _existingReservations

    fun loadExistingReservations(roomId: String) {
        _existingReservations.value = null
        viewModelScope.launch {
            _existingReservations.value = ReservationRepository.getReservationsByRoom(roomId)
        }
    }


    fun isStartTimeInPast(year: Int, month: Int, day: Int, startHour: Int, startMinute: Int): Boolean {
        return ReservationTimeUtils.isStartTimeInPast(year, month, day, startHour, startMinute)
    }

    fun isTimeOverlapping(year: Int, month: Int, day: Int, startHour: Int, startMinute: Int, endHour: Int, endMinute: Int): Boolean {
        val existing = _existingReservations.value ?: return false
        val startTimeStr = ReservationTimeUtils.toReservationTimeString(year, month, day, startHour, startMinute)
        val endTimeStr = ReservationTimeUtils.toReservationTimeString(year, month, day, endHour, endMinute)
        val newStartMs = ReservationTimeUtils.parseReservationTimeMillis(startTimeStr) ?: return false
        val newEndMs = ReservationTimeUtils.parseReservationTimeMillis(endTimeStr) ?: return false

        return ReservationTimeUtils.hasOverlap(newStartMs, newEndMs, existing)
    }

    fun makeReservation(reservation: Reservation) {
        _isSubmitting.value = true
        viewModelScope.launch {
            try {
                // 1. Fetch existing reservations for this room
                val existingReservations = ReservationRepository.getReservationsByRoom(reservation.roomID)
                
                // 2. Check for time overlaps
                val newStartMs = ReservationTimeUtils.parseReservationTimeMillis(reservation.startTime) ?: 0L
                val newEndMs = ReservationTimeUtils.parseReservationTimeMillis(reservation.endTime) ?: 0L
                
                if (newStartMs <= System.currentTimeMillis()) {
                    _errorMessage.value = "이미 지난 시간입니다."
                    _submitResult.value = false
                    return@launch
                }

                val isOverlapping = ReservationTimeUtils.hasOverlap(
                    newStartMs,
                    newEndMs,
                    existingReservations
                )
                
                if (isOverlapping) {
                    _errorMessage.value = "이미 예약된 시간입니다."
                    _submitResult.value = false
                } else {
                    val success = ReservationRepository.addReservation(reservation)
                    if (!success) {
                        _errorMessage.value = "예약 중 오류가 발생했습니다."
                    }
                    _submitResult.value = success
                }
            } catch (e: Exception) {
                _errorMessage.value = "예약 처리 중 오류가 발생했습니다."
                _submitResult.value = false
            } finally {
                _isSubmitting.value = false
            }
        }
    }

    fun clearSubmitResult() {
        _submitResult.value = null
        _errorMessage.value = null
    }
}
