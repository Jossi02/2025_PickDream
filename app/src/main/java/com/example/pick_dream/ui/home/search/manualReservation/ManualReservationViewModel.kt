package com.example.pick_dream.ui.home.search.manualReservation

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Reservation
import com.prolificinteractive.materialcalendarview.CalendarDay
import kotlinx.coroutines.launch

class ManualReservationViewModel : ViewModel() {
    var formState = ManualReservationFormState()
        private set

    var selectedDay: CalendarDay?
        get() = formState.selectedDay
        set(value) { formState = formState.copy(selectedDay = value) }
    var startHour: Int?
        get() = formState.startHour
        set(value) { formState = formState.copy(startHour = value) }
    var startMinute: Int?
        get() = formState.startMinute
        set(value) { formState = formState.copy(startMinute = value) }
    var endHour: Int?
        get() = formState.endHour
        set(value) { formState = formState.copy(endHour = value) }
    var endMinute: Int?
        get() = formState.endMinute
        set(value) { formState = formState.copy(endMinute = value) }
    var selectedEquipments: List<String>
        get() = formState.selectedEquipments
        set(value) { formState = formState.copy(selectedEquipments = value) }

    fun beginRoom(roomId: String) {
        if (formState.roomId != roomId) {
            formState = ManualReservationFormState(roomId = roomId)
        }
    }

    fun updateDetails(
        eventName: String,
        eventDescription: String,
        eventTarget: String,
        eventParticipantsText: String
    ) {
        formState = formState.copy(
            eventName = eventName,
            eventDescription = eventDescription,
            eventTarget = eventTarget,
            eventParticipantsText = eventParticipantsText
        )
    }

    fun resetForm() {
        formState = ManualReservationFormState()
    }

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
            _existingReservations.value = ManualReservationRepository.getReservationsByRoom(roomId)
        }
    }
    fun validateSlot(
        year: Int?,
        month: Int?,
        day: Int?,
        startHour: Int?,
        startMinute: Int?,
        endHour: Int?,
        endMinute: Int?
    ): ManualReservationSlotValidation = ManualReservationValidator.validateSlot(
        year,
        month,
        day,
        startHour,
        startMinute,
        endHour,
        endMinute,
        _existingReservations.value
    )

    fun makeReservation(reservation: Reservation) {
        _isSubmitting.value = true
        viewModelScope.launch {
            try {
                // 1. Fetch existing reservations for this room
                val existingReservations =
                    ManualReservationRepository.getReservationsByRoom(reservation.roomID)
                val validationError =
                    ManualReservationValidator.validateReservation(reservation, existingReservations)

                if (validationError != null) {
                    _errorMessage.value = validationError
                    _submitResult.value = false
                } else {
                    val success = ManualReservationRepository.createReservation(reservation)
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
