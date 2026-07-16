package com.example.pick_dream.ui.home.search.manualReservation

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.navigation.NavOptions
import androidx.navigation.fragment.findNavController
import com.example.pick_dream.R
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.NetworkStatus
import com.example.pick_dream.repository.networkFailure
import com.example.pick_dream.util.ReservationTimeUtils
import com.google.android.material.button.MaterialButton

class ManualReservationInputFragment : Fragment() {
    private val reservationViewModel: ManualReservationViewModel by activityViewModels()

    private lateinit var btnReserve: MaterialButton
    private lateinit var etEventName: EditText
    private lateinit var etEventDetail: EditText
    private lateinit var etEventTarget: EditText
    private lateinit var etEventPeople: EditText
    private var pendingReservationForNotification: Reservation? = null

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_manual_reservation_input, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val btnBack = view.findViewById<View>(R.id.btnBack)
        btnReserve = view.findViewById(R.id.btnReserve)
        etEventName = view.findViewById(R.id.etEventName)
        etEventDetail = view.findViewById(R.id.etEventDetail)
        etEventTarget = view.findViewById(R.id.etEventTarget)
        etEventPeople = view.findViewById(R.id.etEventPeople)
        val tvBuildingInfo = view.findViewById<TextView>(R.id.tvBuildingInfo)
        val tvRoomName = view.findViewById<TextView>(R.id.tvRoomName)

        restoreFormDetails()
        setupWatchers()
        observeViewModel()

        btnBack.setOnClickListener {
            findNavController().popBackStack()
        }

        btnReserve.setOnClickListener {
            handleReservation()
        }

        arguments?.let { args ->
            tvBuildingInfo.text = args.getString("building") ?: ""
            tvRoomName.text = args.getString("roomName") ?: ""
        }
    }

    private fun setupWatchers() {
        val watcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                reservationViewModel.updateDetails(
                    etEventName.text.toString(),
                    etEventDetail.text.toString(),
                    etEventTarget.text.toString(),
                    etEventPeople.text.toString()
                )
                updateButtonState()
            }
            override fun afterTextChanged(s: Editable?) {}
        }
        etEventName.addTextChangedListener(watcher)
        etEventDetail.addTextChangedListener(watcher)
        etEventTarget.addTextChangedListener(watcher)
        etEventPeople.addTextChangedListener(watcher)
        updateButtonState()
    }

    private fun restoreFormDetails() {
        val state = reservationViewModel.formState
        etEventName.setText(state.eventName)
        etEventDetail.setText(state.eventDescription)
        etEventTarget.setText(state.eventTarget)
        etEventPeople.setText(state.eventParticipantsText)
    }

    private fun updateButtonState() {
        val isFilled = etEventName.text.isNotBlank() &&
                etEventDetail.text.isNotBlank() &&
                etEventTarget.text.isNotBlank() &&
                etEventPeople.text.isNotBlank()

        btnReserve.isEnabled = isFilled
        if (isFilled) {
            btnReserve.setBackgroundColor(resources.getColor(R.color.primary_400, null))
            btnReserve.setTextColor(resources.getColor(android.R.color.white, null))
        } else {
            btnReserve.setBackgroundColor(resources.getColor(R.color.primary_050, null))
            btnReserve.setTextColor(resources.getColor(R.color.primary_400, null))
        }
    }

    private fun observeViewModel() {
        reservationViewModel.errorMessage.observe(viewLifecycleOwner) { msg ->
            if (msg != null) {
                Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
                reservationViewModel.clearSubmitResult() // clear error message
            }
        }

        reservationViewModel.submitResult.observe(viewLifecycleOwner) { isSuccess ->
            if (isSuccess == true) {
                pendingReservationForNotification?.let { reservation ->
                    ManualReservationNotificationCoordinator.onReservationCreated(
                        requireContext(),
                        reservation
                    )
                }
                pendingReservationForNotification = null
                showSuccessDialog()
                reservationViewModel.clearSubmitResult()
            }
        }

        reservationViewModel.isSubmitting.observe(viewLifecycleOwner) { isSubmitting ->
            btnReserve.isEnabled = !isSubmitting
            btnReserve.text = if (isSubmitting) "예약 중..." else "대여하기"
        }
    }

    private fun handleReservation() {
        val eventName = etEventName.text.toString()
        val eventDescription = etEventDetail.text.toString()
        val eventParticipants = etEventPeople.text.toString().toIntOrNull() ?: 0
        val eventTarget = etEventTarget.text.toString()

        val roomName = arguments?.getString("roomName") ?: ""
        val roomId = arguments?.getString("roomId").orEmpty()
        val room = com.example.pick_dream.ui.home.search.LectureRoomRepository.lectureRoomsWithFavorites.value
            ?.filterIsInstance<com.example.pick_dream.ui.home.search.ListItem.RoomItem>()
            ?.find {
                it.lectureRoom.roomID == roomId ||
                    (roomId.isBlank() && it.lectureRoom.name == roomName)
            }
            ?.lectureRoom

        val validationError = ManualReservationValidator.validateDetails(
            eventName,
            eventDescription,
            eventTarget,
            eventParticipants,
            room?.capacity
        )
        if (validationError != null) {
            Toast.makeText(context, validationError, Toast.LENGTH_SHORT).show()
            return
        }

        if (!NetworkStatus.hasValidatedInternet()) {
            Toast.makeText(
                context,
                networkFailure("예약 생성").userMessage,
                Toast.LENGTH_SHORT
            ).show()
            return
        }

        UserRepository.getCurrentStudentId { studentId ->
                if (studentId.isNullOrBlank()) {
                    Toast.makeText(context, "학번 정보를 찾을 수 없습니다.", Toast.LENGTH_SHORT).show()
                    return@getCurrentStudentId
                }

                arguments?.let { args ->
                    val canonicalRoomId = args.getString("roomId") ?: ""
                    val startTimeStr = ReservationTimeUtils.toReservationTimeString(
                        args.getInt("selectedYear"),
                        args.getInt("selectedMonth") + 1,
                        args.getInt("selectedDay"),
                        args.getInt("startHour"),
                        args.getInt("startMinute")
                    )
                    val endTimeStr = ReservationTimeUtils.toReservationTimeString(
                        args.getInt("selectedYear"),
                        args.getInt("selectedMonth") + 1,
                        args.getInt("selectedDay"),
                        args.getInt("endHour"),
                        args.getInt("endMinute")
                    )
                    
                    val reservation = Reservation(
                        userID = studentId,
                        roomID = canonicalRoomId,
                        eventName = eventName,
                        eventDescription = eventDescription,
                        eventTarget = eventTarget,
                        eventParticipants = eventParticipants,
                        startTime = startTimeStr,
                        endTime = endTimeStr,
                        status = "대기"
                    )
                    
                    pendingReservationForNotification = reservation
                    reservationViewModel.makeReservation(reservation)
                }
        }
    }

    private fun showSuccessDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_result, null)
        dialogView.findViewById<TextView>(R.id.tvDialogMessage).text = "대여가 완료되었습니다."
        val dialog = androidx.appcompat.app.AlertDialog.Builder(requireContext(), R.style.CustomDialog)
            .setView(dialogView)
            .setCancelable(false)
            .create()
            
        // The dialog background is now handled in XML (bg_rounded_16dp)
        // and R.style.CustomDialog handles the transparent window background.
        
        dialogView.findViewById<TextView>(R.id.btnDialogOk).setOnClickListener {
            dialog.dismiss()
            reservationViewModel.resetForm()
            findNavController().navigate(
                R.id.homeFragment,
                null,
                NavOptions.Builder()
                    .setPopUpTo(R.id.homeFragment, true)
                    .build()
            )
        }
        dialog.show()
    }

    override fun onResume() {
        super.onResume()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.GONE
    }

    override fun onPause() {
        super.onPause()
        requireActivity().findViewById<View>(R.id.nav_view)?.visibility = View.VISIBLE
    }

}
