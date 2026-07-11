package com.example.pick_dream.ui.home.search.manualReservation

import com.prolificinteractive.materialcalendarview.CalendarDay

data class ManualReservationFormState(
    val roomId: String = "",
    val selectedDay: CalendarDay? = null,
    val startHour: Int? = null,
    val startMinute: Int? = null,
    val endHour: Int? = null,
    val endMinute: Int? = null,
    val selectedEquipments: List<String> = emptyList(),
    val eventName: String = "",
    val eventDescription: String = "",
    val eventTarget: String = "",
    val eventParticipantsText: String = ""
)
