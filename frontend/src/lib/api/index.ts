// The only file pages and components may import from. Every action calls the FastAPI backend
// through ./http (spec B10). Errors are ApiError with the backend's code and status.

export * from "./types";
export { ApiError, isApiError, NETWORK_MESSAGE, type ErrorCode } from "./errors";
export { apiUrl } from "./http/client";

// settings / licence / branding
export {
  getPublicSettings,
  getSettings,
  saveSettings,
  uploadBrandingImage,
  clearBrandingImage,
  getLicence,
  getFullLicence,
  applyLicenceKey,
  sendTestEmail,
  sendTestWhatsapp,
  testAiProvider,
  type BrandingKind,
} from "./http/settings";

// auth
export {
  applicantSignUp,
  applicantSignIn,
  type SignUpInput,
  getSetupStatus,
  adminSignUp,
  adminSignIn,
  superAdminSignUp,
  superAdminSignIn,
  updateMyAdminAccount,
  changeMyAdminPassword,
  signOut,
  getSession,
  getPasswordOptions,
  forgotPassword,
  resetPassword,
  type ResetKind,
  updateMyProfile,
  changeMyPassword,
} from "./http/auth";

// catalog / match / agent / fees. There is no delete: items are hidden or closed.
export {
  listCourseGroups,
  getCourse,
  listUniversities,
  getUniversity,
  listVacancies,
  getVacancy,
  listVisaPrograms,
  getVisaProgram,
  getCatalogOptions,
  matchUniversities,
  matchVacancies,
  matchVisaPrograms,
  askAgent,
  rememberAgentInputs,
  lastAgentInputs,
  listAdminCourseGroups,
  saveCourseGroup,
  listAdminCourses,
  saveCourse,
  listAdminUniversities,
  saveUniversity,
  listAdminVacancies,
  saveVacancy,
  listAdminVisaPrograms,
  saveVisaProgram,
  getFees,
  saveFees,
  resetFees,
} from "./http/catalog";

// applications / cases / documents
export {
  startApplication,
  myApplications,
  getMyApplication,
  withdrawApplication,
  payApplicationFee,
  uploadDocument,
  MAX_UPLOAD_BYTES,
  listApplications,
  getApplication,
  changeStage,
  changeStatus,
  updateCase,
  addInternalNote,
  sendCaseEmail,
  listApplicantAccounts,
  resetApplicantPassword,
  listDocuments,
  verifyDocument,
  rejectDocument,
} from "./http/applications";

// money
export {
  getMyPayment,
  myInvoices,
  getMyInvoice,
  requestRefund,
  listPendingPayments,
  verifyPayment,
  rejectPayment,
  listRefunds,
  approveRefund,
  declineRefund,
  listOutstanding,
  sendPaymentReminder,
  listLedger,
  ledgerSummary,
  addLedgerEntry,
  reverseLedgerEntry,
  ledgerCsvUrl,
  listInvoices,
  getInvoice,
} from "./http/money";

// courses / notifications / enquiries / team / audit. Admins are never deleted.
export {
  enrol,
  myEnrolments,
  listEnrolments,
  approveCertificate,
  verifyCertificate,
  listNotifications,
  resendNotification,
  submitEnquiry,
  listEnquiries,
  addEnquiry,
  updateEnquiry,
  addEnquiryNote,
  listAdmins,
  approveAdmin,
  deactivateAdmin,
  resetStaffPassword,
  reactivateAdmin,
  setRole,
  setSections,
  listAssignableAdmins,
  listAudit,
  AUDIT_ROWS_PER_PAGE,
} from "./http/other";

// partner agents and commissions (B16). Agents are switched off, never deleted.
export {
  listAgents,
  createAgent,
  updateAgent,
  setApplicationAgent,
  listCommissions,
  setCommission,
  payCommission,
  cancelCommission,
} from "./http/agents";

// B2B partners and logos (B18). Partners are switched off, never deleted.
export {
  listPublicPartners,
  listPartners,
  createPartner,
  updatePartner,
  uploadPartnerLogo,
  clearPartnerLogo,
} from "./http/partners";
