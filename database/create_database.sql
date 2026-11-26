-- Run once in SSMS with a login allowed to create databases.
USE [master];
GO

IF DB_ID(N'ProCheck') IS NULL
BEGIN
    CREATE DATABASE [ProCheck];
END;
GO
